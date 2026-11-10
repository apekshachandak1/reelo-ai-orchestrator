"""LAYER: SECURITY POLICY. Who may call which tool, and which KB docs they may read."""
ALLOWLIST = {
    "internal_sales":  {"hot_picks", "compliance_filter", "stock_by_warehouse", "vendor_validate", "kb_search", "add_to_basket_stub"},
    "portal_vendor":   {"vendor_validate", "kb_search"},
    "portal_customer": {"hot_picks", "compliance_filter", "kb_search", "add_to_basket_stub"},
}
KB_VISIBILITY = {"internal_sales": ["internal", "public", "vendor"], "portal_vendor": ["public", "vendor"],
                 "portal_customer": ["public"]}
