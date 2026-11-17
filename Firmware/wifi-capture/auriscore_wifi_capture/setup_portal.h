// Temporary WPA2 setup AP. Credentials never leave the AP or appear in HTML/logs.
#pragma once
#include <WebServer.h>
#include <DNSServer.h>
#include <functional>

class WifiSetupPortal {
  WebServer server{80}; DNSServer dns;
  bool active=false, handlers=false;
  uint32_t started=0, rebootAt=0;
  String apName, apKey, csrf, initialHost;
  std::function<bool(const String&,const String&,const String&,const String&,const String&)> save;
  static String escape(String text) {
    text.replace("&","&amp;"); text.replace("<","&lt;"); text.replace(">","&gt;");
    text.replace("\"","&quot;"); text.replace("'","&#39;"); return text;
  }
  bool apRequest() {
    // A server listening on all interfaces must reject configuration over STA/LAN.
    return active && server.client().localIP()==WiFi.softAPIP();
  }
  void headers() {
    server.sendHeader("Cache-Control","no-store");
    server.sendHeader("X-Content-Type-Options","nosniff");
    server.sendHeader("Referrer-Policy","no-referrer");
    server.sendHeader("Content-Security-Policy","default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'");
  }
  void page() {
    headers(); if(!apRequest()) { server.send(403,"text/plain","Setup is available only through the device setup Wi-Fi."); return; }
    if(server.header("Host")!="192.168.4.1") {
      server.sendHeader("Location","http://192.168.4.1/setup");server.send(302,"text/plain","");return;
    }
    String html=F("<!doctype html><html lang='id'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
      "<title>Pengaturan Wi-Fi AurisCore</title><style>body{font:16px system-ui;color:#123d30;background:#f5f8f6;margin:24px auto;padding:0 20px;max-width:480px}"
      "label{display:block;margin-top:18px}input,select,button{box-sizing:border-box;width:100%;font:inherit;padding:12px;border:1px solid #becfc5;border-radius:10px;margin-top:6px}"
      "button{background:#08664b;color:white;margin:24px 0}small{display:block;margin-top:6px}</style>"
      "<h1>Wi-Fi AurisCore</h1><p>Simpan jaringan sekali. Saat dinyalakan berikutnya, alat menyambung otomatis ke profil yang tersedia.</p>"
      "<form method='post' action='/configure'><input type='hidden' name='csrf' value='");
    html+=csrf;
    html+=F("'><label>Nama Wi-Fi / hotspot<input name='ssid' maxlength='32' required autocomplete='off'></label>"
      "<label>Password Wi-Fi<input name='password' type='password' maxlength='63' autocomplete='off'></label>"
      "<label>Jenis jaringan<select name='kind'><option value='wifi'>Wi-Fi router</option><option value='hotspot'>Hotspot HP / data seluler</option></select></label>"
      "<label>Alamat server / gateway<input name='host' maxlength='253' required autocapitalize='none' value='");
    html+=escape(initialHost);
    html+=F("'></label><small>Untuk uji lokal: IP Wi-Fi laptop, tanpa http:// atau nomor port. Setelah server di-host, gunakan alamat yang disepakati.</small>"
      "<label>Kode pairing server<input name='token' type='password' maxlength='128' autocomplete='off'></label>"
      "<small>Kosongkan untuk mempertahankan pairing yang sudah tersimpan. Perangkat baru memerlukan kode pairing dari server.</small>"
      "<button>Simpan dan sambungkan</button></form>"
      "<p>Profil lama dipertahankan; maksimal empat jaringan. Jaringan ini menjadi prioritas. Alat tidak membaca password atau jaringan HP secara otomatis.</p>"
      "<p>Jika server masih di laptop, laptop harus dapat dijangkau pada jaringan pilihan. Pengaturan ini tidak menguji mic atau hasil medis.</p></html>");
    server.send(200,"text/html; charset=utf-8",html);
  }
  void configure() {
    headers();
    if(!apRequest() || server.header("Host")!="192.168.4.1" || server.arg("csrf")!=csrf ||
       (server.hasHeader("Origin") && server.header("Origin")!="http://192.168.4.1")) {
      server.send(403,"text/plain","Invalid setup session. Open http://192.168.4.1/setup again."); return;
    }
    String ssid=server.arg("ssid"), password=server.arg("password"), host=server.arg("host"), token=server.arg("token"), kind=server.arg("kind");
    if(!ssid.length() || ssid.length()>32 || password.length()>63 || !host.length() || host.length()>253 ||
       strpbrk(host.c_str(),"/:?@# \t\r\n") || token.length()>128 || (token.length()>0 && token.length()<16) ||
       (kind!="wifi" && kind!="hotspot")) {
      server.send(400,"text/plain","Pengaturan tidak valid. Periksa panjang nama, password, pairing dan alamat server."); return;
    }
    if(!save(ssid,password,host,token,kind)) { server.send(400,"text/plain","Tidak tersimpan. Periksa pairing atau kapasitas empat profil. Profil lama tidak dihapus."); return; }
    server.send(200,"text/html; charset=utf-8","<!doctype html><meta name='viewport' content='width=device-width,initial-scale=1'><h1>Pengaturan tersimpan</h1><p>Alat akan menyambung otomatis. Kembalikan HP ke Wi-Fi atau hotspot pilihan, lalu buka website AurisCore. Jaringan setup alat akan ditutup.</p>");
    Serial.println("SETUP_PROFILE_SAVED_REBOOTING"); rebootAt=millis()+1000;
  }
public:
  static String randomKey() {
    char key[33]; for(unsigned n=0;n<4;n++)sprintf(key+n*8,"%08lx",(unsigned long)esp_random());
    return String(key);
  }
  void begin(const String &name,const String &key,const String &host,
    std::function<bool(const String&,const String&,const String&,const String&,const String&)> callback) {
    apName=name; apKey=key; initialHost=host; save=callback;
  }
  bool start() {
    if(active)return true;
    if(apKey.length()<8 || !WiFi.mode(WIFI_AP_STA) || !WiFi.softAPConfig(IPAddress(192,168,4,1),IPAddress(192,168,4,1),IPAddress(255,255,255,0)) ||
       !WiFi.softAP(apName.c_str(),apKey.c_str(),1,false,1)) { Serial.println("SETUP_AP_FAILED"); return false; }
    csrf=randomKey(); active=true; started=millis();
    if(!handlers) {
      const char *keys[]={"Host","Origin"}; server.collectHeaders(keys,2);
      server.on("/",HTTP_GET,[this](){page();}); server.on("/setup",HTTP_GET,[this](){page();});
      server.on("/configure",HTTP_POST,[this](){configure();});
      server.onNotFound([this](){
        if(!apRequest()) {server.send(403,"text/plain","Setup AP only");return;}
        server.sendHeader("Location","http://192.168.4.1/setup");server.send(302,"text/plain","");
      }); handlers=true;
    }
    dns.start(53,"*",IPAddress(192,168,4,1)); server.begin();
    Serial.println("SETUP_AP_STARTED"); Serial.print("SETUP_SSID=");Serial.println(apName);
    Serial.println("SETUP_URL=http://192.168.4.1/setup"); return true;
  }
  void tick() {
    if(!active)return;
    dns.processNextRequest();server.handleClient();
    if(rebootAt && (int32_t)(millis()-rebootAt)>=0) { Serial.flush(); ESP.restart(); }
    if(millis()-started>600000) {
      stop();Serial.println("SETUP_AP_CLOSED_TIMEOUT");
    }
  }
  void stop() {
    if(!active)return;
    server.stop();dns.stop();WiFi.softAPdisconnect(false);WiFi.mode(WIFI_STA);
    active=false;csrf="";rebootAt=0;
  }
  bool running()const {return active;}
};
