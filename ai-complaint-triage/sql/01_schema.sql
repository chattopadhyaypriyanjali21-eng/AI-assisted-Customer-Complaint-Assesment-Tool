-- Supabase / Postgres schema for the complaint assessment capstone.
-- Paste into the Supabase SQL editor. Three tables, two views, one enum-ish check set.
-- Deliberately small: intake -> AI draft -> human decision -> reporting views.

create table if not exists products (
  product_id          text primary key,
  product_name        text not null,
  product_family      text,
  regulatory_class    text,
  default_owner_team  text
);

-- 1) What the intake form writes. Nothing here is AI-generated.
create table if not exists complaints (
  complaint_id   text primary key,
  received_at    timestamptz not null default now(),
  channel        text check (channel in ('Web Form','Email','Phone','Distributor Portal')),
  reporter_type  text check (reporter_type in ('Patient','Clinician','Clinic Admin','Distributor')),
  region         text,
  product_text   text,              -- free text as typed by the reporter
  lot_or_serial  text,
  contact_email  text,
  complaint_text text not null,
  status         text not null default 'New'
                 check (status in ('New','AI Assessed','In Human Review','Routed','Closed'))
);

-- 2) What Claude writes. Never overwritten - it is the auditable AI draft of record.
create table if not exists assessment_ai (
  complaint_id        text primary key references complaints(complaint_id) on delete cascade,
  created_at          timestamptz not null default now(),
  model               text not null default 'claude-sonnet-4-5',
  prompt_version      text not null default 'v1',
  category            text not null,
  product_id          text references products(product_id),
  severity            text not null check (severity in ('Critical','High','Medium','Low')),
  priority_score      int  not null check (priority_score between 1 and 100),
  mdr_reportable_flag text not null check (mdr_reportable_flag in ('Yes','No','Possible')),
  summary             text not null,
  key_facts           jsonb not null default '{}'::jsonb,
  missing_info        text[] not null default '{}',
  suggested_next_action text,
  route_team          text not null,
  confidence          numeric(3,2) not null check (confidence between 0 and 1),
  needs_human_review  boolean not null,
  review_reason       text
);

-- 3) What the human handler decides. This is the record the business acts on.
create table if not exists assessment_human (
  complaint_id    text primary key references complaints(complaint_id) on delete cascade,
  reviewed_at     timestamptz not null default now(),
  reviewer        text not null,
  decision        text not null check (decision in ('Accepted','Edited','Rejected')),
  final_category  text not null,
  final_severity  text not null check (final_severity in ('Critical','High','Medium','Low')),
  final_team      text not null,
  final_mdr       boolean not null,
  reviewer_notes  text,
  review_minutes  numeric(5,1)
);

-- The AI draft is a suggestion until a human commits it. Nothing routes on assessment_ai alone
-- when needs_human_review is true.
create or replace view v_complaint_worklist as
select c.complaint_id,
       c.received_at,
       c.region,
       c.reporter_type,
       coalesce(h.final_severity, a.severity)  as severity,
       coalesce(h.final_category, a.category)  as category,
       coalesce(h.final_team,     a.route_team) as owning_team,
       a.priority_score,
       a.summary,
       a.missing_info,
       a.confidence,
       a.needs_human_review,
       h.reviewer,
       h.decision,
       c.status
from complaints c
left join assessment_ai    a using (complaint_id)
left join assessment_human h using (complaint_id);

-- Agreement rate is the metric that tells you whether the model can be trusted to
-- auto-route low-severity work. Watch it every month.
create or replace view v_ai_agreement as
select date_trunc('month', h.reviewed_at)                                   as month,
       count(*)                                                             as reviewed,
       avg((h.final_category = a.category)::int)::numeric(4,3)              as category_agreement,
       avg((h.final_severity = a.severity)::int)::numeric(4,3)              as severity_agreement,
       avg((h.final_team     = a.route_team)::int)::numeric(4,3)            as routing_agreement,
       count(*) filter (where h.final_severity in ('Critical','High')
                          and a.severity in ('Medium','Low'))               as severity_undercalls,
       avg(h.review_minutes)::numeric(5,2)                                  as avg_review_minutes
from assessment_human h
join assessment_ai a using (complaint_id)
group by 1 order by 1;

create index if not exists idx_complaints_status   on complaints(status);
create index if not exists idx_assessment_ai_severity  on assessment_ai(severity, priority_score desc);
