cwlVersion: v1.2
class: CommandLineTool
id: veda-black-marble
label: VEDA Black Marble
doc: >
  Thin OGC wrapper: loads EARTHDATA_TOKEN from MAAP Secrets, then runs
  `uv run blackmarble` against a shallow clone of NASA-IMPACT/veda-black-marble.

hints:
  DockerRequirement:
    dockerPull: mas.maap-project.org/root/maap-workspaces/custom_images/maap_base:v6.0.0

baseCommand: ["/opt/app/run.sh"]

inputs:
  bbox:
    type: string
    doc: Bounding box as min_lon,min_lat,max_lon,max_lat (WGS84)
    inputBinding:
      prefix: --bbox
  date:
    type: string
    doc: Target date YYYY-MM-DD
    inputBinding:
      prefix: --date
  config:
    type: string?
    default: fast
    doc: Preset default | high_quality | fast
    inputBinding:
      prefix: --config
  osm_source:
    type: string?
    default: overpass
    doc: overpass or layercake
    inputBinding:
      prefix: --osm_source
  wgs84:
    type: string?
    default: "false"
    doc: Also export EPSG:4326 (true/false)
    inputBinding:
      prefix: --wgs84
  basename:
    type: string?
    default: black_marble_output
    doc: Output filename stem → output/<basename>.tif (maps to --output-path)
    inputBinding:
      prefix: --basename
  earthdata_secret_name:
    type: string?
    default: EARTHDATA_TOKEN
    doc: MAAP secret name holding the Earthdata token (not the token value)
    inputBinding:
      prefix: --earthdata_secret_name

outputs:
  out:
    type: Directory
    outputBinding:
      glob: output
