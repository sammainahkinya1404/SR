import { Suspense } from "react";
import { Loading } from "@/components/ui";
import { StockTabs } from "@/components/stock/stock-tabs";

// useSearchParams in the tabs needs a Suspense boundary for the build.
export default function StockPage() {
  return (
    <Suspense fallback={<Loading />}>
      <StockTabs />
    </Suspense>
  );
}
