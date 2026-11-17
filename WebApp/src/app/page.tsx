import { MainScreen } from "@/components/auriscore/main-screen";
import { AccountProvider } from "@/components/auriscore/account-panel";

export default function Home() {
  return <AccountProvider><MainScreen /></AccountProvider>;
}
