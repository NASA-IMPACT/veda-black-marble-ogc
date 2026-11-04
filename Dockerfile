FROM mas.maap-project.org/root/maap-workspaces/custom_images/maap_base:v6.0.0

WORKDIR /opt/app
COPY . /opt/app

# Do not copy a local upstream/ tree — build.sh shallow-clones NASA-IMPACT/veda-black-marble
RUN chmod +x /opt/app/run.sh /opt/app/build.sh /opt/app/resolve_earthdata_token.py \
  && /opt/app/build.sh

ENTRYPOINT ["/opt/app/run.sh"]
