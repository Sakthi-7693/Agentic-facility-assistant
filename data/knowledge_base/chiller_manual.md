# Chiller Operating Manual - Carrier 30XA Air-Cooled Screw Chiller

Document ID: KB-CHILLER-30XA-002
Applies to: Chiller-01 (CH-01), Chiller-02 (CH-02)
Revision: 5.0

## 1. Normal Operating Parameters

| Parameter | Normal value | Alarm threshold |
|---|---|---|
| Chilled water supply temperature | 6.5 - 7.0 C | > 8.5 C |
| Chilled water return temperature | 12.0 - 13.0 C | > 15.0 C |
| Delta-T across evaporator | 5.0 - 6.0 C | < 3.5 C |
| Power draw at full load | 180 - 190 kW | > baseline + 15% |
| Condenser approach temperature | 1.5 - 3.0 C | > 4.0 C |
| Evaporator approach temperature | 1.0 - 2.5 C | > 3.5 C |
| Compressor load | up to 100% | sustained 100% |

## 2. High Power Consumption

A chiller drawing more than 15% above its 30-day rolling baseline is
inefficient and must be investigated. Common causes, in order of frequency:

1. **High condenser water temperature.** Every 1 C rise in condenser water
   leaving temperature increases chiller power draw by approximately 2-3%.
   Check the cooling tower fan operation, basin water level and fill fouling.
2. **Fouled condenser tubes.** Increases the condenser approach temperature.
   If approach exceeds 4 C, schedule tube cleaning.
3. **Increased building cooling load.** Verify against the zone temperatures
   and outside air conditions before blaming the equipment.
4. **Low refrigerant charge.** Shows up as low suction pressure together with
   high superheat.
5. **Excessive short cycling.** Check that the chilled water flow is stable.

## 3. Chilled Water Supply Temperature Above Setpoint

If the chiller cannot hold its chilled water setpoint:

1. Confirm the compressor is at or near 100% load. If it is at 100% and still
   cannot reach setpoint, the unit is **capacity limited** - the cooling demand
   exceeds what the chiller can deliver under current conditions.
2. Check condenser heat rejection (cooling tower / condenser fans).
3. Check for low refrigerant charge or a failing compressor.
4. Consider staging the standby chiller to add capacity.

A chiller running at 94% load with a supply temperature 3 C above setpoint and
elevated power draw is almost always suffering from **poor heat rejection**,
not from a compressor failure.

## 4. Staging the Standby Chiller

Only a certified operator may stage chillers. The procedure is:

1. Confirm the standby unit health score is above 80 and it is in `standby`.
2. Verify the chilled water isolation valves are open.
3. Enable the lead/lag changeover from the BMS - never from the local panel.
4. Monitor for 15 minutes; both units should share load evenly.

Chiller staging is an **operational action** and requires supervisor approval
before it may be executed by an automated system.

## 5. Efficiency Reference

- Design efficiency: 0.62 kW per ton of refrigeration.
- A 10% rise in power draw at constant load costs approximately 400 kWh per day
  for an 800 TR unit running 20 hours.
