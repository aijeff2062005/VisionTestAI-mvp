ARG BASE_IMAGE
FROM ${BASE_IMAGE}
COPY --chown=frappe:0 services/hospital/smart-hospital /home/frappe/frappe-bench/apps/smart_hospital
COPY --chown=frappe:0 services/hospital/qy-vision-hospital /home/frappe/frappe-bench/apps/qy_vision_hospital
COPY --chmod=755 deploy/jetson/qy-test/provision.sh /usr/local/bin/qy-provision
USER frappe
WORKDIR /home/frappe/frappe-bench
RUN ./env/bin/pip install -e apps/smart_hospital -e apps/qy_vision_hospital 'paho-mqtt==2.1.0' \
 && mkdir -p assets apps/qy_vision_hospital/qy_vision_hospital/public \
 && ln -sfn ../apps/smart_hospital/smart_hospital/public assets/smart_hospital \
 && ln -sfn ../apps/qy_vision_hospital/qy_vision_hospital/public assets/qy_vision_hospital \
 && ls -1 apps > sites/apps.txt \
 && ./env/bin/python -c 'import erpnext, healthcare, solvronix_desk, smart_hospital, qy_vision_hospital, paho.mqtt.publish'
