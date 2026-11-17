import Link from "next/link";
import { AccountPanel, AccountProvider } from "@/components/auriscore/account-panel";
import { AccountMenu } from "@/components/auriscore/account-menu";

export default function Settings() {
  return <AccountProvider><main className="min-h-screen bg-background px-5 py-10">
    <div className="mx-auto max-w-2xl space-y-6">
      <div className="flex items-center justify-between gap-4">
        <Link href="/" className="inline-flex min-h-11 items-center text-emerald-800 underline">Kembali ke pemeriksaan</Link>
        <AccountMenu />
      </div>
      <div className="space-y-2"><h1 className="text-3xl font-semibold tracking-tight">Settings</h1>
        <p className="text-muted-foreground">Kelola profil dan akun AurisCore.</p></div>
      <AccountPanel />
    </div>
  </main></AccountProvider>;
}
