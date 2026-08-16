# Maintenance Procedures

Document ID: KB-MAINT-005
Revision: 2.4

## 1. Preventive Maintenance Schedule

| Asset type | Interval | Key tasks |
|---|---|---|
| Chiller | Quarterly | Tube inspection, refrigerant check, oil analysis, controls test |
| AHU | 6 months | Filter replacement, belt check, coil clean, damper actuator test |
| Cooling tower | Quarterly | Fill inspection, water treatment, fan gearbox, basin clean |
| VAV box | Annual | Damper calibration, actuator test, sensor calibration |

A preventive maintenance task is **overdue** the day after its due date. Assets
overdue by more than 7 days must be escalated to the facility supervisor.

## 2. Service Request Priorities

| Priority | Definition | Target response |
|---|---|---|
| critical | Safety risk or total loss of cooling to a critical area | 1 hour |
| high | High-criticality asset degraded, occupied zone above 25 C | 4 hours |
| medium | Performance loss without occupant impact, limit exceeded | 24 hours |
| low | Cosmetic, informational, or planned improvement | 5 working days |

## 3. Raising a Service Request

Every service request must include:

1. The affected asset ID.
2. A priority from the table above.
3. A description containing the observed symptom **and** the supporting
   measurements (for example "airflow 6,200 CFM against 9,500 CFM design").
4. Any related active alarm IDs.

Requests are assigned automatically: HVAC assets to the HVAC Team, electrical
assets to the Electrical Team.

## 4. AHU Filter Replacement Procedure

1. Notify the BMS operator and place the AHU in maintenance mode.
2. Lock out and tag out the fan starter.
3. Record the differential pressure before removal.
4. Replace with the specified filter grade (MERV 13 for Building A AHUs).
5. Record the new differential pressure - it should read below 0.6 inWC.
6. Return the unit to automatic and confirm airflow recovers to within 10% of
   design within 10 minutes.

Typical duration: 90 minutes per unit. Two technicians required.

## 5. Post-Repair Verification

After any airflow-related repair, confirm all of the following before closing
the service request:

- Supply airflow within 10% of design.
- Filter differential pressure below 1.2 inWC.
- Served zones back within 1 C of setpoint within two hours.
- Related alarms cleared in the BMS.
