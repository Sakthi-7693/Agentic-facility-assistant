# Safety Instructions

Document ID: KB-SAFETY-006
Revision: 6.0

## 1. Lock-Out / Tag-Out (LOTO)

No work may begin on rotating or electrically powered equipment until LOTO is
applied. The five steps are:

1. Notify all affected personnel and the BMS operator.
2. Shut down the equipment using the normal stop sequence.
3. Isolate all energy sources (electrical, chilled water, refrigerant).
4. Apply a personal lock and tag to each isolation point.
5. Verify zero energy before touching the equipment.

Only the person who applied a lock may remove it.

## 2. Personal Protective Equipment

| Task | Required PPE |
|---|---|
| Plant room entry | Safety shoes, hearing protection |
| Filter replacement | Gloves, N95 mask, safety glasses |
| Refrigerant work | Gloves, face shield, refrigerant monitor |
| Cooling tower work | Harness, gloves, biological hazard precautions |
| Electrical panel work | Arc-flash rated clothing, insulated gloves |

## 3. Refrigerant Safety

Building A chillers use R-134a. The plant room has a fixed refrigerant leak
detector set to alarm at 1,000 ppm. On alarm:

1. Evacuate the plant room immediately.
2. Start the emergency ventilation fan from outside the room.
3. Do not re-enter until the detector reads below 100 ppm.

## 4. Confined Space

Cooling tower basins and large ductwork are confined spaces. A permit, a
standby attendant and continuous atmosphere monitoring are mandatory.

## 5. Legionella Control

Cooling tower water is tested monthly for Legionella. If a count above 1,000
CFU/mL is returned, the tower must be taken offline and disinfected before it
returns to service.

## 6. Automated System Boundaries

An automated or AI system may **read** any facility data at any time. It may
**never** autonomously perform any of the following without explicit human
confirmation:

- Starting, stopping or staging any chiller, pump or fan.
- Changing any temperature or pressure setpoint.
- Overriding or disabling any alarm.
- Creating, modifying or closing a service request.
- Dispatching a technician.

Every such action must be confirmed by a named operator and recorded in the
audit log.
