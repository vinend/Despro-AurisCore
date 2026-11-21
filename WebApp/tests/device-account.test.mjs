import test from "node:test";
import assert from "node:assert/strict";
import { deviceAccountAuthorized } from "../src/lib/auriscore/device-account.server.ts";
import { attachCloudSocket } from "../src/lib/auriscore/cloud-gateway.server.ts";
import { WebSocket, WebSocketServer } from "ws";
import { once } from "node:events";
import { DeviceConnection } from "../src/lib/auriscore/device-connection.ts";
import { cloudOperatorAuthorized } from "../src/lib/auriscore/cloud-analysis.server.ts";
import { createLiveAnalysisHandler } from "../src/lib/auriscore/live-analysis-route.server.ts";
import Redis from "ioredis";

test("a browser retries a busy lease and stops if the owner persists", t => {
  t.mock.timers.enable({ apis: ["Date", "setTimeout", "setInterval"], now: 1000 });
  const sockets = [];
  class Socket {
    constructor() { sockets.push(this); }
    close() {}
  }
  const previous = globalThis.WebSocket;
  globalThis.WebSocket = Socket;
  t.after(() => { globalThis.WebSocket = previous; });
  const errors = [];
  const connection = new DeviceConnection({ url: "wss://example.invalid", token: "" }, {
    onError: message => errors.push(message),
  });
  t.after(() => connection.close());
  const busy = () => sockets.at(-1).onclose({ code: 1013, reason: "Controller slot busy" });
  connection.connect();
  busy();
  t.mock.timers.tick(1000);
  assert.equal(sockets.length, 2);
  assert.deepEqual(errors, []);
  t.mock.timers.tick(20000);
  busy();
  assert.match(errors[0], /sesi lain/);
  t.mock.timers.tick(5000);
  assert.equal(sockets.length, 2);
});

test("fresh account credentials are requested on each connection and late credentials cannot authenticate a closed socket",async t=>{
  const previous=globalThis.WebSocket;const sockets=[];
  class Socket {
    static OPEN=1;readyState=1;sent=[];
    constructor(){sockets.push(this);}
    send(value){this.sent.push(JSON.parse(value));}
    close(){this.readyState=3;this.onclose?.({code:1000});}
  }
  globalThis.WebSocket=Socket;t.after(()=>{globalThis.WebSocket=previous;});
  let finish,calls=0;
  const connection=new DeviceConnection({url:'wss://fixture.invalid',token:'',getToken:()=>{
    calls++;return calls===1?new Promise(resolve=>{finish=resolve;}):Promise.resolve('refreshed-account-token');
  }},{});
  t.after(()=>connection.close());
  connection.connect();const pending=sockets[0].onopen();connection.close();finish('old-account-token');await pending;
  assert.deepEqual(sockets[0].sent,[]);
  connection.connect();await sockets[1].onopen();
  assert.equal(calls,2);assert.equal(sockets[1].sent[0].token,'refreshed-account-token');
  connection.close();
  let reject,attempts=0;const errors=[];
  const retried=new DeviceConnection({url:'wss://fixture.invalid',token:'',getToken:()=>++attempts===1
    ?new Promise((_resolve,rejected)=>{reject=rejected;}):Promise.resolve('current-account-token')},{onError:message=>errors.push(message)});
  t.after(()=>retried.close());
  retried.connect();const lateFailure=sockets[2].onopen();retried.close();retried.connect();await sockets[3].onopen();
  reject(new Error('Old session failed'));await lateFailure;
  assert.equal(sockets[3].readyState,Socket.OPEN);assert.deepEqual(errors,[]);
});

test("device access verifies confirmed provider identity and explicit assignment, never a shared pairing token", async t => {
  const env={NEXT_PUBLIC_SUPABASE_URL:'https://fixture.supabase.co',NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY:'fixture-key',AURISCORE_DEVICE_ACCOUNT_EMAILS:'owner@example.invalid'};
  for(const [key,value] of Object.entries(env)){const previous=process.env[key];process.env[key]=value;t.after(()=>{if(previous===undefined)delete process.env[key];else process.env[key]=previous;});}
  const jwt=(suffix,exp=Math.floor(Date.now()/1000)+100)=>`header.${Buffer.from(JSON.stringify({exp})).toString('base64url')}.${suffix}`;
  let identity={id:'fixture',email:'owner@example.invalid',email_confirmed_at:'2026-11-21'};
  const request=t.mock.method(globalThis,'fetch',async (url,options)=>{
    assert.equal(String(url),'https://fixture.supabase.co/auth/v1/user');
    assert.match(options.headers.Authorization,/^Bearer /);
    return Response.json(identity);
  });
  assert.equal(await deviceAccountAuthorized('old-shared-pairing-token'),false);
  assert.equal(request.mock.callCount(),0);
  assert.equal(await deviceAccountAuthorized(jwt('valid')),true);
  assert.equal(await deviceAccountAuthorized(jwt('valid')),true);
  assert.equal(request.mock.callCount(),1);
  identity={...identity,email:'other@example.invalid'};
  assert.equal(await deviceAccountAuthorized(jwt('other')),false);
  identity={...identity,email:'owner@example.invalid',email_confirmed_at:null};
  assert.equal(await deviceAccountAuthorized(jwt('unconfirmed')),false);
  identity={...identity,email_confirmed_at:'2026-11-21'};
  assert.equal(await deviceAccountAuthorized(jwt('expired',1)),false);
  request.mock.mockImplementation(async()=>new Response(null,{status:401}));
  assert.equal(await deviceAccountAuthorized(jwt('rejected-provider')),false);
  process.env.AURISCORE_DEVICE_ACCOUNT_EMAILS='';
  assert.equal(await deviceAccountAuthorized(jwt('unconfigured')),false);
});

test("cloud browser authorization rejects before any Redis lease or stream control",async t=>{
  const server=new WebSocketServer({port:0});await once(server,'listening');
  server.on('connection',socket=>attachCloudSocket(socket,'browser',{url:'rediss://127.0.0.1:1',namespace:'denied',token:'legacy-fixture-token',authorize:async()=>false}));
  t.after(()=>{for(const client of server.clients)client.terminate();server.close();});
  const client=new WebSocket(`ws://127.0.0.1:${server.address().port}`);
  await once(client,'open');client.send(JSON.stringify({type:'authenticate',token:'legacy-fixture-token'}));
  assert.equal((await once(client,'close'))[0],1008);
});

test("production analysis fails closed without account assignment and accepts only a verified assigned session",async t=>{
  const env={VERCEL:'1',NEXT_PUBLIC_SUPABASE_URL:'https://fixture.supabase.co',NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY:'fixture-key',
    AURISCORE_DEVICE_ACCOUNT_EMAILS:'',AURISCORE_OPERATOR_TOKEN:'old-shared-fixture',
    AURISCORE_INFERENCE_URL:'https://inference.example',AURISCORE_INFERENCE_TOKEN:'inference-fixture'};
  for(const [key,value] of Object.entries(env)){const previous=process.env[key];process.env[key]=value;t.after(()=>{if(previous===undefined)delete process.env[key];else process.env[key]=previous;});}
  const request=token=>new Request('https://app.example/api/analysis/live?mode=heart',{method:'POST',
    headers:{'Content-Type':'application/octet-stream','X-AurisCore-Start-Sample':'0','X-AurisCore-Operator-Token':token},body:new Uint8Array(160000)});
  assert.equal(await cloudOperatorAuthorized(request(env.AURISCORE_OPERATOR_TOKEN)),false);
  process.env.AURISCORE_DEVICE_ACCOUNT_EMAILS='owner@example.invalid';
  const token=`header.${Buffer.from(JSON.stringify({exp:Math.floor(Date.now()/1000)+100})).toString('base64url')}.http-fixture`;
  const calls=[];
  t.mock.method(globalThis,'fetch',async(url,options)=>{
    calls.push(String(url));
    if(String(url)==='https://fixture.supabase.co/auth/v1/user'){
      assert.equal(options.headers.Authorization,`Bearer ${token}`);
      return Response.json({id:'owner',email:'owner@example.invalid',email_confirmed_at:'2026-11-21'});
    }
    assert.equal(String(url),'https://inference.example/v1/analysis/heart/pcm');
    assert.equal(options.headers.Authorization,'Bearer inference-fixture');
    return new Response(null,{status:429});
  });
  const handler=createLiveAnalysisHandler(()=>assert.fail('Production must not use the local worker'));
  assert.equal((await handler(request(env.AURISCORE_OPERATOR_TOKEN))).status,401);
  assert.equal(calls.length,0);
  assert.equal((await handler(request(token))).status,429);
  assert.equal(calls.length,2);
});

test("account revalidation does not block relay heartbeat and revocation closes control",{timeout:4000},async t=>{
  // Isolated Redis transport double; this verifies queue behavior, not Redis delivery.
  for(const [method,result] of Object.entries({connect:undefined,set:'OK',subscribe:1,eval:1,exists:0})){
    t.mock.method(Redis.prototype,method,async()=>result);
  }
  t.mock.method(Redis.prototype,'disconnect',()=>{});
  let now=Date.now(),checks=0,finish,checking;
  const revalidation=new Promise(resolve=>{checking=resolve;});
  t.mock.method(Date,'now',()=>now);
  const server=new WebSocketServer({port:0});await once(server,'listening');
  server.on('connection',socket=>attachCloudSocket(socket,'browser',{url:'redis://127.0.0.1:1',namespace:'fixture',token:'unused',authorize:async()=>{
    if(++checks===1)return true;
    checking();return new Promise(resolve=>{finish=resolve;});
  }}));
  t.after(()=>{for(const client of server.clients)client.terminate();server.close();});
  const client=new WebSocket(`ws://127.0.0.1:${server.address().port}`);
  const messages=[];client.on('message',raw=>messages.push(JSON.parse(String(raw))));
  await once(client,'open');client.send(JSON.stringify({type:'authenticate',token:'account-fixture'}));
  while(!messages.some(m=>m.type==='authenticated'))await new Promise(resolve=>setTimeout(resolve,5));
  now+=31000;
  await revalidation;
  client.send(JSON.stringify({type:'heartbeat',id:'while-provider-is-pending'}));
  const deadline=performance.now()+1000;
  while(!messages.some(m=>m.type==='heartbeat_ack')&&performance.now()<deadline)await new Promise(resolve=>setTimeout(resolve,5));
  assert.ok(messages.some(m=>m.type==='heartbeat_ack'),'Account provider blocked the relay queue');
  finish(false);
  assert.equal((await once(client,'close'))[0],1008);
});
