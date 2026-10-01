"use client";

import { useQuery } from "@tanstack/react-query";
import { api, call } from "@/lib/api";
import { Button, ErrorText, Loading, Modal } from "./ui";

/** Plain-text receipt from the backend (32 columns: 58 mm printers, SMS, WhatsApp). */
export function ReceiptText({ saleId }: { saleId: string }) {
  const receipt = useQuery({
    queryKey: ["receipt", saleId],
    queryFn: () => call(api.GET("/sales/{sale_id}/receipt", { params: { path: { sale_id: saleId } } })),
  });
  if (receipt.isPending) return <Loading />;
  if (receipt.error) return <ErrorText error={receipt.error} />;
  return (
    <pre className="receipt mx-auto w-fit rounded-md bg-gray-50 p-4 font-mono text-xs leading-5 ring-1 ring-gray-200">
      {receipt.data.text}
    </pre>
  );
}

export function ReceiptModal({
  saleId,
  onClose,
  closeLabel = "Close",
}: {
  saleId: string;
  onClose: () => void;
  closeLabel?: string;
}) {
  const share = async () => {
    const receipt = await call(
      api.GET("/sales/{sale_id}/receipt", { params: { path: { sale_id: saleId } } }),
    );
    // Opens WhatsApp with the receipt; the customer's number is chosen there.
    window.open(`https://wa.me/?text=${encodeURIComponent(receipt.text)}`, "_blank", "noopener");
  };
  return (
    <Modal open onClose={onClose} title="Receipt">
      <ReceiptText saleId={saleId} />
      <div className="mt-4 flex flex-wrap justify-end gap-2">
        <Button variant="secondary" onClick={() => window.print()}>
          Print
        </Button>
        <Button variant="secondary" onClick={share}>
          Share on WhatsApp
        </Button>
        <Button onClick={onClose}>{closeLabel}</Button>
      </div>
    </Modal>
  );
}
