// Shapes returned by the API. They mirror backend/app/schemas.py.

export type User = {
  id: number;
  email: string;
  name: string;
  role: "user" | "admin";
  plan: string;
  is_active: boolean;
  created_at: string;
};

export type Plan = {
  name: string;
  label: string;
  price_usd_month: number;
  daily_messages: number;
  daily_tokens: number;
  burst_per_minute: number;
  max_output_tokens: number;
};

export type Quota = {
  plan: string;
  messages_used: number;
  messages_limit: number;
  tokens_used: number;
  tokens_limit: number;
  resets_at: string;
};

export type Conversation = { id: number; title: string; created_at: string; updated_at: string };

export type Message = {
  id: number;
  role: "user" | "assistant";
  content: string;
  status: "complete" | "stopped" | "error";
  created_at: string;
};

export type DayUsage = {
  date: string;
  messages: number;
  tokens: number;
  cost_usd: number;
  active_users: number;
};

export type AccountUsage = { quota: Quota; plan: Plan; last_7_days: DayUsage[] };

export type AdminOverview = {
  days: number;
  today: DayUsage;
  totals: {
    users: number;
    messages: number;
    tokens: number;
    cost_usd: number;
    failed_requests: number;
    monthly_revenue_usd: number;
  };
  plans: { plan: string; users: number }[];
  series: DayUsage[];
};

export type AdminUser = {
  id: number;
  email: string;
  name: string;
  role: string;
  plan: string;
  is_active: boolean;
  created_at: string;
  messages_today: number;
  messages_limit: number;
  tokens_today: number;
  messages_30d: number;
  tokens_30d: number;
  cost_30d_usd: number;
  last_used_at: string | null;
};
