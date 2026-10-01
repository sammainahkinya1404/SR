import { redirect } from "next/navigation";

// Stock goes in on the Stock page (Add Stock tab).
export default function AddStockPage() {
  redirect("/stock?tab=add");
}
