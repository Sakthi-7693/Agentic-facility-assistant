# Troubleshooting FAQ

Document ID: KB-FAQ-009
Revision: 2.2

**Q: A zone is warm but the AHU reports normal supply air temperature. Where do
I look first?**
A: Look at the airflow, not the temperature. Cold air that never arrives cannot
cool a room. Check the AHU supply airflow against design and check the VAV
damper position for that zone.

**Q: What filter differential pressure means the filter must be changed?**
A: Above 1.2 inWC. Above 1.8 inWC the restriction is severe and airflow will
already have dropped by 30-40%.

**Q: The chiller is drawing more power than usual. Is it failing?**
A: Not necessarily. Check condenser heat rejection first. High condenser water
temperature raises chiller power by 2-3% for every 1 C. Cooling tower fouling
is a far more common cause than compressor failure.

**Q: How do I know which chiller serves a particular zone?**
A: Use the asset relationship map. Never assume from asset numbering.

**Q: Two faults appear at once - which is the root cause?**
A: Work from the symptom back through the air path, then the water path. A
starved zone points to the AHU; a warm chilled water supply points to the plant.
Where both are abnormal, the one whose trend started earlier is usually the
root cause.

**Q: When should the standby chiller be started?**
A: Only when the lead chiller is at 100% load and cannot hold setpoint, and only
with supervisor approval. Chiller staging is an operational action.

**Q: How long does an AHU filter replacement take?**
A: About 90 minutes with two technicians, including verification.

**Q: What temperature counts as a comfort breach?**
A: Outside 21 - 24 C for more than 60 minutes during occupied hours.

**Q: Can the AI assistant create a service request by itself?**
A: No. It may prepare the request and recommend it, but a human must confirm
before it is submitted.

**Q: Where do I find the design airflow for an AHU?**
A: In the equipment specification document, or from `get_asset_details` in the
BMS which returns the design capacity for each unit.
