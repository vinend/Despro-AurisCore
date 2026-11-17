import { AccountEntry } from "@/components/auriscore/account-entry";
import { AccountProvider } from "@/components/auriscore/account-panel";

export default function Home() {
  return <AccountProvider><AccountEntry /></AccountProvider>;
}
