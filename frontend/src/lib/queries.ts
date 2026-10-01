"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, call } from "./api";

// Shared lookups used across several pages. Page-specific queries live with their pages.

export function useProducts(includeInactive = false) {
  return useQuery({
    queryKey: ["products", { includeInactive }],
    queryFn: () =>
      call(api.GET("/products", { params: { query: { include_inactive: includeInactive } } })),
  });
}

export function useAccounts(enabled = true) {
  return useQuery({
    queryKey: ["accounts"],
    queryFn: () => call(api.GET("/accounts")),
    enabled,
  });
}

export function useCategories() {
  return useQuery({
    queryKey: ["expense-categories"],
    queryFn: () => call(api.GET("/expense-categories")),
  });
}

export function useCustomers(q?: string) {
  return useQuery({
    queryKey: ["customers", { q: q ?? "" }],
    queryFn: () => call(api.GET("/customers", { params: { query: { q: q || undefined } } })),
  });
}

/** After a posting, many views change together (stock, cash, alerts...): refresh them all. */
export function useRefreshAll() {
  const client = useQueryClient();
  return () => client.invalidateQueries();
}
