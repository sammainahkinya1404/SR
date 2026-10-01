import { redirect } from "next/navigation";

// The product list now lives on the Stock page (Available Stock tab).
export default function ProductsPage() {
  redirect("/stock");
}
