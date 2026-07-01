export type Role = "user" | "assistant";

export type AssetType = "post" | "image" | "deck" | "pdf" | "campaign" | "video";

export interface Asset {
  id: number;
  campaign_id: number | null;
  type: AssetType;
  title: string;
  body: Record<string, unknown>;
  file_url: string | null;
  meta: Record<string, unknown>;
}

export interface Folder {
  id: number;
  name: string;
  employee_count: number;
  created_at?: string | null;
}

export interface Employee {
  id: number;
  folder_id: number;
  name: string;
  role: string;
  file_url?: string | null;
  created_at?: string | null;
}

export interface ChatMessage {
  role: Role;
  content: string;
  pending?: boolean;
  assets?: Asset[];
  // Tappable quick-pick replies the Create agent offers under a conversational question.
  chips?: string[];
  // Files the user attached on THIS turn — snapshotted onto the message so the transcript shows them
  // next to the prompt (live-session only; not persisted with the conversation).
  attachments?: Attachment[];
}

export interface Attachment {
  id: number;
  name: string;
  text: string;
  kind: string; // image | pdf | text
  chars: number;
  // Client-side object URL for an image attachment, captured at attach time so the transcript can show
  // a real thumbnail instantly (live session only — blob URLs don't survive a reload).
  previewUrl?: string;
}

export interface Conversation {
  id: number;
  title: string;
  kind?: string;
}

export interface CampaignSummary {
  id: number;
  name: string;
  type?: string; // "internal" (promote Talentrupt) | "external" (client-targeting)
  created_at: string | null;
  sector?: string; // resolved target sector — used to avoid creating a duplicate same-sector folder
}

export interface CampaignItem {
  id: number;
  campaign_id: number;
  scheduled_date: string | null;
  channel: string;
  format: string; // post | image | deck | pdf
  topic: string;
  hook: string;
  status: string; // planned | generated
  asset: Asset | null;
}

export interface ClientStrategy {
  why_fit?: string;
  pain_points?: string[];
  approach?: string;
  talking_points?: string[];
  recommended_services?: string[];
  first_touch?: string;
}

export interface CampaignProspect {
  id: number;
  campaign_id: number;
  company: string;
  fit_score: number;
  segment: string;
  sector?: string;
  hiring_signal: string;
  why_now: string;
  recommended_service: string;
  contacts: { name?: string; role?: string; linkedin?: string; email?: string }[];
  timing: { reach_now?: boolean; label?: string; reason?: string };
  source: string;
  company_linkedin?: string;
  status: string;
}

export interface CampaignDetail extends CampaignSummary {
  goal: string;
  audience: string;
  pillar: string;
  channels: string[];
  timeline: string;
  kpis: string[];
  strategy: Record<string, unknown>;
  status: string;
  resolved_sector?: string;
  conversation_id?: number | null; // the internal campaign's chat thread
  items?: CampaignItem[];
  assets: Asset[];
}

export interface Brand {
  name: string;
  tagline: string;
  voice: string;
  pillars: string[];
  services: string[];
  proof_points: string[];
  brand_kit: {
    palette?: Record<string, string>;
    fonts?: Record<string, string>;
    visual_rules?: string[];
    tagline?: string;
  };
}

export interface Health {
  status: string;
  llm_provider: string;
  llm_ready: boolean;
  enrichment_ready?: boolean;
  database: string;
}

export interface BusinessProfile {
  key: string;
  label: string;
  description: string;
}

export interface OutreachContent {
  email_subject?: string;
  email_body?: string;
  linkedin_message?: string;
  followups?: { day: number; message: string }[];
  talking_points?: string[];
}

export interface VerifiedContact {
  name?: string;
  role?: string;
  linkedin?: string;
  email?: string;
  verified?: boolean;
  source?: string;
}

export interface OutreachLog {
  channel?: string;
  sent_at?: string | null;
  replied_at?: string | null;
  meeting_at?: string | null;
  notes?: string;
  history?: { event: string; at: string; channel?: string; note?: string }[];
}

export interface Opportunity {
  id: number;
  company: string;
  segment: string;
  fit_score: number;
  hiring_signal: string;
  pain_point: string;
  recommended_service: string;
  status: string;
  saved?: boolean;
  country?: string;
  why: {
    why_fit?: string;
    why_now?: string;
    contacts?: { name?: string; role?: string; linkedin?: string; email?: string }[];
    verified_contacts?: VerifiedContact[];
    timing?: { reach_now?: boolean; label?: string; reason?: string };
    decision_maker?: string;
    decision_maker_linkedin?: string;
    decision_maker_email?: string;
    website?: string;
    source?: string;
    pain_points?: string[];
    outreach?: OutreachContent;
    outreach_log?: OutreachLog;
  };
  company_linkedin?: string;
  created_at: string | null;
}

export interface BizTask {
  id: number;
  opportunity_id: number | null;
  title: string;
  kind: string;
  due_at: string | null;
  status: string;
  payload?: Record<string, unknown>;
  created_at?: string | null;
}

export interface AnalyticsSummary {
  opportunities: {
    by_status: Record<string, number>;
    by_sector: { sector: string; count: number }[];
    total: number;
    saved: number;
  };
  outreach: { sent: number; replied: number };
  campaigns: { total: number; planning: number; active_clients: number };
  assets: { by_type: Record<string, number> };
  tasks: { overdue: number; due_soon: number; pending: number };
}

export interface KnowledgeStatus {
  source_files: number;
  brand_chunks: number;
  by_folder: Record<string, number>;
  vision_enabled: boolean;
  zip_present: boolean;
}
