const PUMA_SECTION = [
  {
    label: "BATCHES",
    endpoints: [
      { id: "upload",       label: "Upload PDFs",      method: "POST", path: "/batches/upload/",     icon: "⬆" },
      { id: "batch-list",   label: "List Batches",     method: "GET",  path: "/batches/",            icon: "≡", action: "list",  listType: "batch" },
    ]
  },
];

const IMAGE_SECTIONS = [
  {
    label: "BATCHES",
    endpoints: [
      { id: "upload", label: "Upload Folders", method: "POST", path: "/folder/upload/", icon: "⬆" },
      { id: "batch-list", label: "List Batches", method: "GET", path: "/folder/batches/", icon: "≡", action: "list", listType: "batch" },
    ],
  },
  {
    label: "REPORTS",
    endpoints: [
      { id: "report-list", label: "List Reports", method: "GET", path: "/folder/reports/", icon: "≡", action: "list", listType: "report" },
    ],
  },
];

const AUDIT_SECTIONS = [
  {
    label: "UPLOAD",
    endpoints: [
      {
        id: "audit-upload", label: "Upload Excel Files", method: "POST", path: "/upload/", icon: "⬆",
      },
    ],
  },
  {
    label: "BATCHES",
    endpoints: [
      { id: "audit-batch-list", label: "List Batches", method: "GET", path: "/batches/", icon: "≡", action: "list", },
      { id: "audit-batch-detail", label: "Batch Detail", method: "GET", path: "/batches/<pk>/", icon: "◎", action: "view", },
      { id: "audit-batch-logs", label: "Batch Logs", method: "GET", path: "/batches/<pk>/", icon: "∷", action: "logs", },
    ],
  },
  {
    label: "EXPORT",
    endpoints: [
      { id: "audit-export", label: "Download Summary", method: "GET", path: "/export/", icon: "⬇", },
    ],
  },
  {
    label: "RETRY",
    endpoints: [
      { id: "audit-retry-search", label: "Search Blocked", method: "GET", path: "/retry/search/", icon: "⌕", },
      { id: "audit-retry-download", label: "Download Error JSON", method: "GET", path: "/retry/<pk>/download/", icon: "⬇", action: "download", },
      { id: "audit-retry-upload", label: "Upload Fixed JSON", method: "POST", path: "/retry/upload/", icon: "⬆", },
    ],
  },
  {
    label: "SETTINGS",
    endpoints: [
      { id: "audit-settings-buyers", label: "Manage Buyers", method: "GET", path: "/buyers/", icon: "◈",
      },
      { id: "audit-settings-factories", label: "Manage Factories", method: "GET", path: "/factories/", icon: "◈", },
      { id: "audit-settings-pairs", label: "Manage Pairs", method: "GET", path: "/pairs/", icon: "◈", },
    ],
  },
];

const TOP_FIVE_SECTIONS = [
  {
    label: "JOBS",
    endpoints: [
      { id: "top5-upload", label: "Upload Excel", method: "POST", path: "/top-five/upload/", icon: "⬆", },
      { id: "top5-job-list", label: "List Jobs", method: "GET", path: "/top-five/jobs/", icon: "≡", action: "list", },
    ],
  },
];

const MAIL_FETCH_SECTIONS = [
  {
    label: "ACCOUNTS",
    endpoints: [
      { id: "mailfetch-accounts-list", label: "List Mailboxes", method: "GET", path: "/mail-fetch/accounts/", icon: "≡", action: "list" },
    ],
  },
  {
    label: "OAUTH",
    endpoints: [
      // Redirect flow, not a JSON endpoint -- navigate the browser
      // (window.location.href = path), don't fetch/axios this one.
      { id: "mailfetch-oauth-start", label: "Connect Mailbox (admin)", method: "GET", path: "/mail-fetch/oauth/start/", icon: "🔗", action: "redirect" },
    ],
  },
  {
    label: "SEARCH",
    endpoints: [
      { id: "mailfetch-search-start", label: "Start Search", method: "POST", path: "/mail-fetch/search/", icon: "⌕" },
      { id: "mailfetch-search-job", label: "Get Search Job", method: "GET", path: "/mail-fetch/search/{id}/", icon: "≡", action: "retrieve" },
      // Not an HTTP endpoint -- WebSocket connection for job progress.
      { id: "mailfetch-search-ws", label: "Search Progress (WS)", method: "WS", path: "/ws/mail-fetch/jobs/{id}/progress/", icon: "↯", action: "socket" },
    ],
  },
  {
    label: "DOWNLOADS",
    endpoints: [
      { id: "mailfetch-download-single", label: "Download Attachment", method: "GET", path: "/mail-fetch/download/", icon: "⬇" },
      { id: "mailfetch-download-zip", label: "Download Selected as ZIP", method: "POST", path: "/mail-fetch/download-zip/", icon: "⬇" },
    ],
  },
  {
    label: "HISTORY",
    endpoints: [
      { id: "mailfetch-history-list", label: "List Download History", method: "GET", path: "/mail-fetch/history/", icon: "≡", action: "list" },
    ],
  },
];

export const MENU_GROUPS = [
  { title: "PUMA", sections: PUMA_SECTION, },
  { title: "DEFECT_IMAGE", sections: IMAGE_SECTIONS, },
  { title: "AUDIT SUMMARY", sections: AUDIT_SECTIONS, },
  { title: "Top-5", sections: TOP_FIVE_SECTIONS, },
  { title: "MAIL FETCH",   sections: MAIL_FETCH_SECTIONS },
];

export const MENU_BY_SERVICE = {
  puma: PUMA_SECTION,
  image: IMAGE_SECTIONS,
  audit: AUDIT_SECTIONS,
  "mail-fetch": MAIL_FETCH_SECTIONS,
  "top-five": TOP_FIVE_SECTIONS,
};

export const SERVICE_BY_PATH = {
  puma: "puma",
  image: "image",
  audit: "audit",
  "top-five": "top-five",
  "mail-fetch": "mail-fetch",
};