import { createClient } from "@supabase/supabase-js";

// Vercel 환경변수 (VITE_ 접두사 필수 - 브라우저 노출용 공개키만)
const url = import.meta.env.VITE_SUPABASE_URL;
const anon = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY;

export const supabase = createClient(url, anon, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true,
  },
});

// 텔레그램 봇 username (딥링크용). Vercel 환경변수로 주입.
export const TELEGRAM_BOT_USERNAME = import.meta.env.VITE_TELEGRAM_BOT_USERNAME || "";
