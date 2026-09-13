# Odoo 19 image with the Python dependencies needed by roekish_delivery_dpd.
FROM odoo:19.0

USER root
# roulier -> DPD France label generation (e-Station web service).
RUN pip3 install --no-cache-dir --break-system-packages roulier
USER odoo
