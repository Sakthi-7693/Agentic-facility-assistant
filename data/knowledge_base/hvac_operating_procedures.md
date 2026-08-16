# HVAC Operating Procedures

Document ID: KB-HVAC-OPS-001
Revision: 4.2

## 1. What is an AHU?

An **Air Handling Unit (AHU)** is the equipment that conditions and circulates
air through a building. A typical AHU contains a supply fan, a return fan,
filters, a cooling coil, a heating coil, and mixing dampers for outside and
return air. The AHU takes return air from the occupied space, mixes it with
fresh outside air, passes it across the cooling coil, and delivers conditioned
supply air to the zones through ductwork and VAV boxes.

Key AHU measurements are supply airflow (CFM), supply air temperature, filter
differential pressure, fan speed, and chilled water valve position.

## 2. What is a Chiller?

A **chiller** removes heat from water and delivers chilled water to the AHU
cooling coils. Building A uses two air-cooled screw chillers in a lead/lag
arrangement, with a cooling tower rejecting condenser heat.

## 3. What is a VAV box?

A **Variable Air Volume (VAV)** box sits between the AHU duct and the occupied
zone. It modulates a damper to control how much supply air each zone receives.
When a VAV damper is fully open (100%) and the zone is still warm, the zone is
being starved of supply air from upstream.

## 4. Daily Operating Sequence

| Time | Action |
|---|---|
| 06:00 | Optimum start - AHUs ramp up, chiller plant enabled |
| 08:00 | Occupied mode, zone setpoint 22 C +/- 1 C |
| 12:00 | Peak load check - verify chiller staging |
| 18:00 | Unoccupied mode, setpoint relaxed to 26 C |
| 22:00 | Night purge if outside air temperature below 18 C |

## 5. Standard Setpoints

- Occupied zone temperature: **22 C** (acceptable band 21 - 24 C)
- Relative humidity: 45 - 60%
- Chilled water supply: **6.7 C**
- Supply air temperature: 12 - 14 C
- Minimum outside air: 15% of supply airflow

## 6. Cooling Mode Operation

In cooling mode the building runs the chiller plant, the AHUs modulate their
chilled water valves to hold supply air temperature, and the VAV boxes modulate
airflow to hold zone temperature. A zone that drifts more than 2 C above
setpoint for over 60 minutes raises a temperature deviation alarm.

## 7. Fault Investigation Order

When a zone is too warm, investigate from the zone outwards:

1. Zone / VAV level - damper position, sensor accuracy, internal heat gain.
2. AHU level - supply airflow, supply air temperature, filter condition.
3. Plant level - chilled water temperature, chiller power, condenser heat
   rejection.

Always confirm which assets actually serve the affected zone before drawing a
conclusion. Use the asset relationship map rather than assuming.
