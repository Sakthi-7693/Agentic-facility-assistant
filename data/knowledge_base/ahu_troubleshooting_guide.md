# AHU Troubleshooting Guide

Document ID: KB-AHU-TS-004
Applies to: Trane M-Series CSAA Air Handling Units (AHU-01, AHU-02, AHU-03)
Revision: 3.1

## 1. Low Supply Airflow

Low airflow is reported when measured supply airflow falls more than 15% below
the design airflow while the supply fan is commanded above 80% speed.

### 1.1 Checklist - perform in this order

1. **Check the filter differential pressure.** A dirty filter is the cause in
   roughly 60% of low airflow cases. Replace the filter bank when differential
   pressure exceeds **1.2 inWC**. A reading above 1.8 inWC means the filter is
   severely blocked and airflow may drop by 30-40%.
2. **Check that dampers are open.** Confirm the outside-air, return-air and
   mixed-air dampers respond to their commands. A stuck damper actuator will
   hold airflow low even with clean filters.
3. **Check the fan belt (belt-driven units only).** A slipping or broken belt
   causes airflow loss while the motor still reports normal speed.
4. **Check the VFD output frequency.** Compare the commanded speed against the
   actual output Hz. A VFD in current-limit will not deliver commanded speed.
5. **Check for a coil blockage.** A fouled or frosted cooling coil adds static
   pressure and reduces airflow.
6. **Check downstream VAV dampers.** If all VAV boxes are wide open and still
   starved, the problem is upstream at the AHU, not in the zone.

### 1.2 Expected readings for a healthy unit

| Parameter | Healthy range |
|---|---|
| Filter differential pressure | 0.4 - 1.2 inWC |
| Supply airflow vs design | within 10% |
| Supply air temperature | 12 - 14 C in cooling mode |
| Fan speed at design load | 65 - 85% |

If the fan is running above 95% speed and airflow is still low, the restriction
is mechanical (filter, damper, coil) and **not** a control problem.

## 2. Supply Air Temperature Too High

1. Verify chilled water is available and the valve is modulating.
2. Check the chilled water supply temperature at the AHU inlet. If it is more
   than 2 C above the plant setpoint, the fault is in the chiller plant, not
   the AHU.
3. Check for a stuck chilled water control valve.
4. Check for excessive outside air intake during peak ambient temperature.

## 3. Zone Too Warm While AHU Reports Normal

1. Confirm the zone is actually served by the AHU under investigation using the
   asset relationship map.
2. Check the VAV damper position. A damper at 100% with low airflow means the
   zone is starved of supply air.
3. Check for unexpected internal heat gain (server equipment, blocked diffusers).
4. Check the zone temperature sensor calibration.

## 4. Escalation Rules

- Raise a **high priority** service request when airflow is more than 30% below
  design, or when a high-criticality asset serves an occupied zone that is more
  than 3 C above setpoint.
- Raise a **medium priority** request for filter replacement when differential
  pressure exceeds the limit but airflow is still within 20% of design.
- Any AHU whose preventive maintenance is overdue by more than 7 days must be
  flagged in the weekly operations report.
