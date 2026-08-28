# Everlab Application Catalog

This document describes the applications represented in this sanitized
portfolio snapshot, why they exist, and the important Everlab-specific design
decisions applied to them. It is an architectural index, not a production
inventory or a replacement for the linked manifests. The private operational
repository remains authoritative for the live environment.

Last reviewed: 2026-08-20

## Shared conventions

- The operational design reconciles `main` through the app-of-apps hierarchy
  under `kubernetes/bootstrap/prod`; this public snapshot is not connected to
  production.
- Internal HTTP applications use Cilium Gateway API through
  `gateway/everlab-gateway` at `192.168.12.100`, normally with a
  `*.prod.everlab.dev` hostname and the IPA-issued wildcard certificate.
- `plex.everlab.dev` is the currently defined directly public HTTPRoute. Public
  exposure and TLS are intentionally reviewed separately from internal routes.
- External Secrets Operator reads the OpenBao KV v2 `secret` mount through the
  cluster-wide `ClusterSecretStore/everlab-secrets`. Secret values are never
  stored in this repository.
- Shared persistent application data normally uses the retained `nfs`
  StorageClass backed by `192.168.21.120:/kubedata`. Git-managed PVCs carry
  Argo CD prune/delete protection.
- `postgres-local` is retained OpenEBS LocalPV storage at
  `/mnt/db-data/postgres` and is restricted to nodes labeled
  `everlab.dev/postgres-storage=true`. It is used only where local database I/O
  is intentional.
- Prometheus collects Kubernetes/node metrics for every workload. Native
  application metrics are enabled when they add useful operational signals;
  the blackbox exporter checks the internal HTTP endpoints that do not expose
  suitable native metrics. Alloy forwards pod logs to Loki.
- Unless called out below, workloads use normal Kubernetes pod networking and
  remain portable across general workers.

## Bootstrap and ownership applications

These applications form the Argo CD ownership graph. They deploy other Argo CD
Applications rather than end-user workloads.

| Argo application | Namespace | Purpose and custom configuration |
| --- | --- | --- |
| [`everlab-prod`](kubernetes/bootstrap/prod/root-application.yaml) | `argocd` | External bootstrap entry point. Owns the three production layer applications and is intentionally not included beneath itself. |
| [`prod-infrastructure`](kubernetes/bootstrap/prod/infrastructure.yaml) | `argocd` | Registers cluster prerequisites from `kubernetes/infrastructure`. |
| [`prod-platform`](kubernetes/bootstrap/prod/platform.yaml) | `argocd` | Registers shared controllers and services from `kubernetes/platform`. |
| [`prod-applications`](kubernetes/bootstrap/prod/applications.yaml) | `argocd` | Registers end-user workloads and their app-of-apps parents from `kubernetes/applications`. |

## Infrastructure applications

| Argo application | Namespace | Purpose and custom configuration |
| --- | --- | --- |
| [`gateway-api`](kubernetes/infrastructure/gateway-api/application.yaml) | `default` | Installs the experimental Gateway API v1.6.1 CRDs. Pruning is disabled to protect cluster-wide API definitions. |
| [`cilium`](kubernetes/infrastructure/cilium/application.yaml) | `kube-system` | Primary CNI, kube-proxy replacement, native routing, L2 announcements, load-balancing, Envoy, and Gateway API controller. Uses `ens18.11` and `ens18.12`, API endpoint `192.168.11.100:6443`, and exports agent/operator/Envoy metrics. |
| [`cert-manager`](kubernetes/infrastructure/cert-manager/application.yaml) | `cert-manager` | Certificate lifecycle controller. Defines the FreeIPA ACME issuer, Let's Encrypt issuer, and internal CA resources; DNS-01 resolution is pinned to `192.168.10.103`. Native controller metrics are enabled. |
| [`external-dns`](kubernetes/infrastructure/external-dns/application.yaml) | `external-dns` | Publishes Service, Ingress, and HTTPRoute records for `prod.everlab.dev` through RFC2136. Uses upsert-only TXT ownership and an OpenBao-delivered TSIG secret. |
| [`gateway`](kubernetes/infrastructure/gateway/application.yaml) | `gateway` | Owns `everlab-gateway`, internal/public wildcard certificates, and listeners. The Cilium Gateway address is `192.168.12.100`; routes from all namespaces are permitted. |
| [`nfs-csi`](kubernetes/infrastructure/nfs-csi/application.yaml) | `kube-system` | Installs the upstream NFS CSI driver and retained `nfs` StorageClass. Dynamic PVCs use NFS 4.1 and per-PVC subdirectories under `192.168.21.120:/kubedata`. |
| [`openebs-localpv`](kubernetes/infrastructure/openebs-localpv/application.yaml) | `kube-system` | Installs the LocalPV hostpath provisioner. The generic chart StorageClass is disabled; repository-managed classes define the allowed local paths and retained lifecycle. |
| [`nvidia-gpu-operator`](kubernetes/infrastructure/nvidia-gpu-operator/application.yaml) | `gpu-operator` | Supplies the NVIDIA toolkit, device plugin, GPU feature discovery, and DCGM exporter while relying on host-installed drivers. Time slicing advertises four A2000 shares and two P1000 shares; MIG and CDI are disabled. |
| [`generic-device-plugin`](kubernetes/infrastructure/hardware-enablement/generic-device-plugin/application.yaml) | `kube-system` | Runs only on `radio-controllers=true` nodes and maps `/dev/ttyUSB0` and `/dev/ttyACM0` to `everlab.dev/zigbee` and `everlab.dev/zwave`. It is privileged because it accesses kubelet device-plugin state and host `/dev`. |
| [`multus`](kubernetes/infrastructure/multus/application.yaml) | `kube-system` | Installs Multus as the secondary CNI used by workloads with an explicit macvlan attachment, including Plex. |
| [`metrics-server`](kubernetes/infrastructure/metrics-server/application.yaml) | `kube-system` | Supplies the Kubernetes resource metrics API for `kubectl top`, autoscaling consumers, Homepage, and Goldilocks. Kubelet TLS verification is disabled for the current node certificate arrangement. |
| [`cloudflared`](kubernetes/infrastructure/cloudflared/application.yaml) | `cloudflared` | Runs the Cloudflare Tunnel connector using an OpenBao-delivered tunnel token. It is monitored through the connector's native metrics listener. |

## Platform applications

| Argo application | Namespace | Purpose and custom configuration |
| --- | --- | --- |
| [`argocd`](kubernetes/platform/argocd/application.yaml) | `argocd` | GitOps controller and UI at `argocd.prod.everlab.dev`. Gateway TLS terminates before the HTTP server, so `server.insecure` is enabled. Server, controller, repository, ApplicationSet, and notification metrics are collected. Pruning is deliberately disabled for this self-managing application. |
| [`kube-prometheus-stack`](kubernetes/platform/kube-prometheus-stack/application.yaml) | `monitoring` | Prometheus, Alertmanager, Grafana, kube-state-metrics, and node exporter. Prometheus retains seven days/8 GB and discovers monitors/rules across all namespaces. Prometheus, Grafana, and Alertmanager use prune-protected NFS PVCs. Kubeadm controller-manager, scheduler, and etcd monitors are disabled because those endpoints currently listen locally. Grafana is at `grafana.prod.everlab.dev`. |
| [`prometheus-blackbox-exporter`](kubernetes/platform/prometheus-blackbox-exporter/application.yaml) | `monitoring` | Performs one-minute HTTPS availability checks for internal application routes. The probe trusts the IPA CA, validates TLS, and treats successful, redirect, and expected authentication-challenge statuses as reachable. It is not externally exposed. |
| [`loki`](kubernetes/platform/loki/application.yaml) | `monitoring` | Seven-day central log store in single-binary/TSDB filesystem mode with a retained 10 Gi NFS PVC. Authentication and caches are disabled; the gateway and per-node canaries are enabled and monitored. |
| [`alloy`](kubernetes/platform/alloy/application.yaml) | `monitoring` | DaemonSet log collector. Discovers pod logs under `/var/log/pods`, parses CRI records, adds namespace/pod/container/app plus `cluster=everlab-prod`, and writes to the Loki gateway. Native metrics are collected. |
| [`external-secrets`](kubernetes/platform/external-secrets/application.yaml) | `external-secrets` | Reconciles ExternalSecrets from OpenBao. Owns the `everlab-secrets` ClusterSecretStore and monitors the controller, webhook, and certificate controller. |
| [`openbao`](kubernetes/platform/openbao/application.yaml) | `openbao` | Central KV v2 secret store at `openbao.prod.everlab.dev`. Runs a single standalone file-storage server on a retained NFS PVC with Shamir manual unseal. A cluster-only metrics listener on port 9101 serves only `/v1/sys/metrics`; its configuration checksum is recorded, while the StatefulSet remains `OnDelete` to make restarts explicit. |
| [`trust-manager`](kubernetes/platform/trust-manager/application.yaml) | `cert-manager` | Distributes trust bundles and a default CA package. CRDs are retained, secret targets are disabled, and controller metrics are collected. |
| [`cloudnative-pg`](kubernetes/platform/cloudnative-pg/application.yaml) | `cnpg-system` | Cluster-wide PostgreSQL operator. Uses the pinned PostgreSQL operator image, exports operator metrics, and owns the retained `postgres-local` StorageClass definition. Individual database clusters remain separate application children. |
| [`kyverno`](kubernetes/platform/kyverno/application.yaml) | `kyverno` | Kubernetes policy engine with admission, background, cleanup, and reports controllers. Each controller has explicit resource limits and native metrics. Argo CD uses server-side diff including mutations. |
| [`descheduler`](kubernetes/platform/descheduler/application.yaml) | `kube-system` | Runs every 15 minutes to correct duplicate placement, taints, required affinity, anti-affinity, and topology spread. PVC pods receive extra eviction protection, and each run is capped at 3 evictions per node, 5 per namespace, and 10 total. |
| [`reloader`](kubernetes/platform/reloader/application.yaml) | `argocd` | Watches ConfigMaps and Secrets cluster-wide and restarts annotated workloads when their inputs change. Runs hardened with a read-only root filesystem and exports a PodMonitor. |
| [`mosquitto`](kubernetes/platform/mosquitto/application.yaml) | `mosquitto` | Shared MQTT broker for automation and bridge workloads. Anonymous access is disabled; an init container generates the password file from OpenBao credentials. Persistent messages use a retained 1 Gi NFS PVC. |
| [`influxdb`](kubernetes/platform/influxdb/application.yaml) | `influxdb` | InfluxDB 2.7 telemetry store. Initial admin, organization, bucket, retention, and token values come from OpenBao. Data uses a retained NFS PVC and `/metrics` is scraped natively. |
| [`telegraf`](kubernetes/platform/telegraf/application.yaml) | `telegraf` | Converts selected SolarEdge and Xcel/Home Assistant MQTT topics into InfluxDB metrics every ten seconds. MQTT credentials and the InfluxDB token come from OpenBao. |
| [`headlamp`](kubernetes/platform/headlamp/application.yaml) | `headlamp` | Kubernetes operations UI at `headlamp.prod.everlab.dev`; in-cluster mode is enabled and Helm actions are disabled. The `headlamp-operator` role grants broad read access plus pod deletion/exec/attach/port-forward and workload scaling, but not mutation of GitOps-owned manifests. |
| [`goldilocks`](kubernetes/platform/goldilocks/application.yaml) | `goldilocks` | Resource recommendation dashboard at `goldilocks.prod.everlab.dev`. Recommendations are on by default, the VPA updater is disabled so recommendations are advisory, and both VPA recommender and admission-controller metrics are collected. |

## End-user and integration applications

### Standalone services

| Argo application | Namespace | Purpose and custom configuration |
| --- | --- | --- |
| [`actual-budget`](kubernetes/applications/actualbudget/application.yaml) | `actual-budget` | Personal budgeting and encrypted sync service at `actual-budget.prod.everlab.dev`. Password-only login, trusted private proxy ranges, 100 MB upload/sync limits, Recreate updates, and a protected 20 Gi NFS data PVC. |
| [`code-server`](kubernetes/applications/code-server/application.yaml) | `code-server` | Browser development environment at `code.prod.everlab.dev`. Login password comes from OpenBao. User config, code-server state, and Codex state use a protected NFS home PVC; projects use the intentionally static retained `192.168.21.120:/projects` PV. |
| [`frigate`](kubernetes/applications/frigate/application.yaml) | `frigate` | Video NVR at `frigate.prod.everlab.dev`. Currently a portable CPU-only placeholder: MQTT, cameras, and recording are disabled. Config/media use protected NFS PVCs, cache and shared memory use RAM, and detector/service metrics are scraped from `/api/metrics`. |
| [`homeassistant`](kubernetes/applications/home-assistant/application.yaml) | `homeassistant` | Home automation core at `homeassistant.prod.everlab.dev`. Uses the app-template chart, Recreate updates, a protected 10 Gi NFS `/config`, conservative probes/resources, and no direct USB or host networking at present. |
| [`homepage`](kubernetes/applications/homepage/application.yaml) | `homepage` | Read-only homelab dashboard at `homepage.prod.everlab.dev`. Repository-managed config covers services, widgets, bookmarks, Kubernetes, Docker, Proxmox, CSS, and JavaScript. Its RBAC can list cluster/Gateway/metrics objects but cannot mutate them. |
| [`n8n`](kubernetes/applications/n8n/application.yaml) | `n8n` | Workflow automation at `n8n.prod.everlab.dev`. Configured for one trusted proxy hop, HTTPS webhook/editor URLs, task runners, filesystem binary data, protected NFS state, and native Prometheus metrics including workflow IDs. |
| [`ntfy`](kubernetes/applications/ntfy/application.yaml) | `ntfy` | Push notification server at `ntfy.prod.everlab.dev`. Login is enabled, default topic access is read-write, cache/attachments live on protected NFS storage, and a separate port exposes native delivery/request metrics. |
| [`plex`](kubernetes/applications/plex/application.yaml) | `plex` | Media server at `plex.prod.everlab.dev` and the public `plex.everlab.dev` route. It is pinned to `prod-k8w-01`, consumes one P1000 GPU share for transcoding, and receives LAN address `192.168.10.50` through Multus. Config uses NFS, media is a static read-only retained PV, and transcode uses retained node-local storage. |
| [`radicale`](kubernetes/applications/radicale/application.yaml) | `radicale` | CalDAV/CardDAV service at `dav.prod.everlab.dev`. Uses owner-only rights, multifilesystem storage on protected NFS, an OpenBao-managed htpasswd file, cached authentication, browser login, masked passwords, and a restrictive CSP. |
| [`trek`](kubernetes/applications/trek/application.yaml) | `trek` | Travel planning application at `trek.prod.everlab.dev`. Runs SQLite with Recreate updates, separate protected NFS data/uploads PVCs, secure proxy/cookie settings, and explicit internal-network access for integrations such as Immich. Admin and encryption values come from OpenBao. |

### AI group

| Argo application | Namespace | Purpose and custom configuration |
| --- | --- | --- |
| [`ai`](kubernetes/applications/ai/application.yaml) | `argocd` | App-of-apps owner for the AI services. It solely owns the shared `ai` Namespace used by Faster Whisper and Piper. |
| [`faster-whisper`](kubernetes/applications/ai/faster-whisper/application.yaml) | `ai` | Wyoming speech-to-text service for Home Assistant. Uses the English `small-int8` model on CPU, exposes port 10300 internally, and persists downloaded models on NFS. |
| [`piper`](kubernetes/applications/ai/piper/application.yaml) | `ai` | Wyoming text-to-speech service using `en_US-lessac-medium`. Exposes port 10200 internally and persists downloaded voice models on NFS. |
| [`ollama`](kubernetes/applications/ai/ollama/application.yaml) | `ollama` | Local LLM runtime pinned to the RTX A2000 and requesting one time-sliced GPU. Cloud access is disabled; one model/request is loaded at a time, flash attention and q8 KV cache are enabled, and models persist on NFS. |
| [`open-webui`](kubernetes/applications/ai/open-webui/application.yaml) | `open-webui` | Chat UI at `open-webui.prod.everlab.dev`, connected to the in-cluster Ollama service. Sign-up is enabled with the default `user` role, and backend data persists on NFS. |

### Bridges and physical integrations

| Argo application | Namespace | Purpose and custom configuration |
| --- | --- | --- |
| [`bridges`](kubernetes/applications/bridges/application.yaml) | `argocd` | App-of-apps owner for MQTT, device, and energy integrations. |
| [`esphome`](kubernetes/applications/bridges/esphome/application.yaml) | `esphome` | ESPHome device build/management UI at `esphome.prod.everlab.dev`. Configuration persists on NFS; no physical device passthrough or device definitions are configured yet. |
| [`ring-mqtt`](kubernetes/applications/bridges/ring-mqtt/application.yaml) | `ring-mqtt` | Publishes Ring events to the shared Mosquitto broker. An init container builds a mode-0600 config from OpenBao credentials; camera streams, modes, and panic controls are currently disabled. State persists on NFS. |
| [`solaredge2mqtt`](kubernetes/applications/bridges/solaredge2mqtt/application.yaml) | `solaredge2mqtt` | Polls the SolarEdge Modbus endpoint at `192.168.30.11:1502` every five seconds and publishes retained Home Assistant discovery/data to Mosquitto. MQTT credentials are injected into an ephemeral generated secrets file. |
| [`xcel-itron2mqtt`](kubernetes/applications/bridges/xcel-itron2mqtt/application.yaml) | `xcel-itron2mqtt` | Reads the Xcel/Itron meter at `192.168.30.10:8081` and publishes Home Assistant topics to Mosquitto. Client certificates persist on NFS and are initialized by the application image. |
| [`zigbee2mqtt`](kubernetes/applications/bridges/zigbee2mqtt/application.yaml) | `zigbee2mqtt` | Zigbee coordinator and UI at `zigbee.prod.everlab.dev`. Runs only on `radio-controllers=true`, requests `everlab.dev/zigbee`, uses the shared Mosquitto credentials, enables Home Assistant discovery, and retains `/app/data` on NFS. |
| [`zwave-js-ui`](kubernetes/applications/bridges/zwave-js-ui/application.yaml) | `zwave-js-ui` | Z-Wave controller/UI at `zwave.prod.everlab.dev`. Runs only on `radio-controllers=true`, requests `everlab.dev/zwave`, exposes UI and WebSocket ports, and retains its store on NFS. |
| [`radio-operators`](kubernetes/applications/radio-operators/application.yaml) | `argocd` | Reserved empty app-of-apps boundary for future radio operators. Pruning remains disabled so it cannot remove workloads that were moved under Bridges. |

### Matrix

| Argo application | Namespace | Purpose and custom configuration |
| --- | --- | --- |
| [`matrix-pg`](kubernetes/applications/matrix/postgres/application.yaml) | `matrix` | Single-instance CNPG PostgreSQL 17 cluster for Synapse. Uses C locale, a protected retained 20 Gi NFS volume, and a PodMonitor for database metrics. |
| [`matrix`](kubernetes/applications/matrix/synapse/application.yaml) | `matrix` | Synapse homeserver at `matrix.prod.everlab.dev`. Registration and statistics reporting are disabled; media/signing state persists on NFS, PostgreSQL pooling is bounded at 5-10 connections, and native Synapse metrics use a separate listener. |
| [`element`](kubernetes/applications/matrix/element/application.yaml) | `matrix` | Element web client at `element.prod.everlab.dev`. It is fixed to the Everlab homeserver, disallows custom homeserver URLs and guests, and uses no persistent storage. |

### Immich

| Argo application | Namespace | Purpose and custom configuration |
| --- | --- | --- |
| [`immich-pg`](kubernetes/applications/immich/postgres/application.yaml) | `immich` | Single-instance CNPG PostgreSQL 17 database on the retained node-local `postgres-local` class for higher I/O performance. The cluster and storage are prune/delete protected. |
| [`immich`](kubernetes/applications/immich/immich/application.yaml) | `immich` | Photo library at `immich.prod.everlab.dev`. API and background workers are split: background processing uses one P1000 share and CUDA machine learning uses one A2000 share. The library uses protected NFS, the family-photo export is a static read-only NFS PV, model cache persists on NFS, and Valkey is ephemeral. Separate Services/ServiceMonitors scrape both worker metric ports. |

### Forgejo

| Argo application | Namespace | Purpose and custom configuration |
| --- | --- | --- |
| [`forgejo-pg`](kubernetes/applications/forgejo/postgres/application.yaml) | `forgejo` | Single-instance CNPG PostgreSQL 17 database on a protected retained 20 Gi NFS volume with native database monitoring. |
| [`forgejo`](kubernetes/applications/forgejo/forgejo/application.yaml) | `forgejo` | Rootless Git forge at `forgejo.prod.everlab.dev` with embedded SSH advertised as `git.prod.everlab.dev`. Uses CNPG, LFS, private repositories by default, offline avatars/resources, sign-in-required viewing, protected NFS data, OpenBao application secrets, and native metrics. |

### NocoDB

| Argo application | Namespace | Purpose and custom configuration |
| --- | --- | --- |
| [`nocodb-pg`](kubernetes/applications/nocodb/postgres/application.yaml) | `nocodb` | Single-instance CNPG PostgreSQL 17 database on a protected retained 10 Gi NFS volume with native database monitoring. |
| [`nocodb`](kubernetes/applications/nocodb/noco-db/application.yaml) | `nocodb` | Collaborative database UI at `nocodb.prod.everlab.dev`. Runs one web pod plus one worker, uses CNPG and a local Valkey deployment, disables telemetry, permits 100 MB request bodies, and receives database/cache/application secrets from OpenBao. |

### Paperless-ngx

| Argo application | Namespace | Purpose and custom configuration |
| --- | --- | --- |
| [`paperless-pg`](kubernetes/applications/paperless-ngx/postgres/application.yaml) | `paperless-ngx` | Single-instance CNPG PostgreSQL 17 database on protected retained 10 Gi NFS storage. Native monitoring is enabled and the declared backup retention policy is 30 days. |
| [`paperless-ngx`](kubernetes/applications/paperless-ngx/paperless-ngx/application.yaml) | `paperless-ngx` | Document ingestion/OCR service at `paperless.prod.everlab.dev`. Uses CNPG and Valkey, recursively tags consumption subdirectories, polls every 30 seconds, stores files as year/correspondent/title, and has separate protected NFS data/media/export/consume PVCs. Secrets come from OpenBao. |

### Vikunja

| Argo application | Namespace | Purpose and custom configuration |
| --- | --- | --- |
| [`vikunja-pg`](kubernetes/applications/vikunja/postgres/application.yaml) | `vikunja` | Single-instance CNPG PostgreSQL 17 database on protected retained 10 Gi NFS storage with native monitoring. |
| [`vikunja`](kubernetes/applications/vikunja/vikunja/application.yaml) | `vikunja` | Task/project manager at `vikunja.prod.everlab.dev`. Registration and CalDAV are enabled, uploaded files are limited to 100 MB and persist on NFS, and PostgreSQL/application secrets come from OpenBao. |

### Wiki.js

| Argo application | Namespace | Purpose and custom configuration |
| --- | --- | --- |
| [`wiki-js-pg`](kubernetes/applications/wiki-js/postgres/application.yaml) | `wiki-js` | Single-instance CNPG PostgreSQL 17 database on protected retained 20 Gi NFS storage with native monitoring. |
| [`wiki-js`](kubernetes/applications/wiki-js/wiki-js/application.yaml) | `wiki-js` | Internal wiki at `wiki.prod.everlab.dev`. Uses CNPG credentials from OpenBao, runs as a non-root single instance, and treats the container's `/wiki/data` as temporary because durable content is stored in PostgreSQL. |

### UniFi

| Argo application | Namespace | Purpose and custom configuration |
| --- | --- | --- |
| [`unifi-parent`](kubernetes/applications/unifi/application.yaml) | `unifi` | App-of-apps owner for the UniFi application and its MongoDB dependency; owns their shared namespace and ExternalSecret. |
| [`unifi-mongo`](kubernetes/applications/unifi/mongo/application.yaml) | `unifi` | MongoDB 8 backing store initialized for UniFi with credentials from OpenBao and protected NFS storage. |
| [`unifi`](kubernetes/applications/unifi/unifi/application.yaml) | `unifi` | UniFi Network Application at `unifi.prod.everlab.dev`. A same-pod Nginx sidecar converts the application's self-signed HTTPS backend to HTTP for Gateway routing. A LoadBalancer exposes native inform, STUN, discovery, portal, speed-test, and syslog ports; configuration persists on NFS. |

### Media group

The media parent owns the shared `media` Namespace, common UID/GID/time-zone
settings, and the retained static `media-data` PV/PVC backed by
`192.168.21.121:/plex`. Child applications own only their workload-specific
configuration volumes.

| Argo application | Namespace | Purpose and custom configuration |
| --- | --- | --- |
| [`media`](kubernetes/applications/media/application.yaml) | `media` | App-of-apps owner plus shared settings/storage. The media PV is 100 TiB, ReadWriteMany, NFS 4.1, `Retain`, and available to the remaining media services. |
| [`ersatztv`](kubernetes/applications/media/ersatztv/application.yaml) | `media` | Custom linear-channel streaming service at `ersatztv.prod.everlab.dev`. It requests a time-sliced P1000 GPU for transcoding, retains configuration and media state on NFS, and uses retained node-local transcode storage. |
| [`hyperhdr`](kubernetes/applications/media/hyperhdr/application.yaml) | `media` | Ambient lighting controller at `hyperhdr.prod.everlab.dev`; exposes HTTP, FlatBuffers, and JSON ports and stores configuration on NFS. |
| [`music-assistant`](kubernetes/applications/media/music-assistant/application.yaml) | `media` | Music aggregation/player server at `music-assistant.prod.everlab.dev`. Uses host networking for LAN discovery/casting, persists its data on NFS, and mounts shared media read-only. |

## Updating this catalog

Update the relevant entry whenever a change alters an application's purpose,
ownership, hostname, secret dependencies, persistence, hardware placement,
network attachment, monitoring model, or other non-obvious behavior. Routine
image/chart version bumps do not require duplicating the version here because
the linked manifest is authoritative.
