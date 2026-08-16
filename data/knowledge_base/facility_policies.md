# Facility Policies

Document ID: KB-POLICY-008
Revision: 3.0

## 1. Comfort Policy

Occupied zones are maintained at 22 C with an acceptable band of 21 - 24 C and
relative humidity between 45% and 60%. A zone outside this band for more than
60 minutes during occupied hours is a comfort breach and must be logged.

## 2. Energy Policy

- Building energy use is measured daily against a rolling 30-day baseline.
- Consumption more than 10% above baseline for two consecutive days triggers an
  energy investigation.
- Chiller plant efficiency is reviewed monthly against the 0.62 kW/TR design.
- Night purge is used whenever outside air temperature is below 18 C.

## 3. Operating Hours

| Period | Hours | Setpoint |
|---|---|---|
| Occupied | 08:00 - 18:00, Mon-Fri | 22 C |
| Extended | 18:00 - 21:00, Mon-Fri | 24 C |
| Unoccupied | All other times | 26 C |

Out-of-hours conditioning requires a written request 24 hours in advance.

## 4. Access Control

Plant rooms are restricted to authorised maintenance staff. Contractors require
an escort and a signed permit to work. All plant room entries are logged.

## 5. Data and Automation Policy

- All BMS data is retained for 24 months.
- Automated agents have **read-only** access to live facility data by default.
- Any write action (service requests, setpoint changes, equipment staging) must
  pass through an explicit human confirmation step and be written to the audit
  log with the operator identity.
- AI-generated recommendations are advisory. The responsible engineer remains
  accountable for the decision.

## 6. Escalation Contacts

| Situation | Contact | Response |
|---|---|---|
| Comfort complaint | Facility Helpdesk | 4 hours |
| Equipment failure | HVAC Team lead | 1 hour |
| Safety incident | EHS Officer | Immediate |
| Power outage | Electrical Team | Immediate |
