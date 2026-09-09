# Deploying against a Synology NAS

Everything here happens once. Budget half a day, most of it waiting for
the first index to finish.

---

## 1. Decide where it runs

| | On the Synology (Container Manager) | On a separate Linux host |
|---|---|---|
| Extra hardware | None | A mini PC on the same LAN |
| Share access | Local bind mount, no CIFS | CIFS mount over SMB |
| TLS | DSM reverse proxy | Caddy, included |
| Indexing load | Competes with file serving | Isolated |
| Needs | x86_64 Plus/XS model, 8 GB RAM free | 8+ cores, 16-32 GB RAM |

**Run it on the Synology if** it is a Plus or XS series (x86_64) with at
least 8 GB of RAM and it is not already busy. This is the cheaper path
and worth trying first.

**Run it on a separate host if** the Synology is a J or Value series
(ARM — the container will not run at all), has under 8 GB of RAM, or
already serves a busy office. Initial indexing pins every core for hours;
on a loaded NAS that is felt by everyone opening files.

Check the model: DSM → **Control Panel → Info Center**. The CPU line says
the architecture.

> You can start on the Synology and move later. The index is a Docker
> volume; moving it is a copy, not a rebuild.

---

## 2. Prepare the Synology

These steps are the same either way.

**a. Create the indexer's service account.**
Control Panel → **User & Group** → Create. Name it `rag-indexer`.
Give it **Read only** on the shared folders that should be searchable and
**No access** on everything else. Under "Applications", deny everything
except file services — this account never signs in to DSM.

Excluding a folder from search is exactly this: don't grant read on it.
There is no second exclusion list to maintain.

**b. Confirm SMB is on and modern.**
Control Panel → **File Services → SMB**. Enable SMB. Under Advanced, set
the maximum protocol to **SMB3** and the minimum to at least **SMB2**.

**c. Note the share name.**
Control Panel → **Shared Folder**. The name in that list is what goes in
`RAG_NAS_SHARE`. Its path on disk is `/volume1/<share>`.

**d. Check the folder permissions are real.**
Open a few shared folders → Edit → Permissions. If everyone has read
access to everything, then everyone will be able to search everything —
the assistant inherits these permissions exactly, and cannot be stricter
than the NAS itself. Fix the permissions first if this is not what you
want.

**e. If you use Active Directory or LDAP.**
Control Panel → **Domain/LDAP**. Note whether it is joined. If it is,
people sign in with their directory username, and you can later enable
the ACL pre-filter. If it is not, local Synology accounts work fine —
only the pre-filter is unavailable.

---

## 3a. Install on the Synology

**Enable SSH**: Control Panel → **Terminal & SNMP** → Enable SSH service.
Install **Container Manager** from Package Center.

```bash
ssh admin@nas.local
sudo -i
mkdir -p /volume1/docker/rag && cd /volume1/docker/rag
git clone <your repo url> .

cp .env.example .env
vi .env                      # fill in the required block
```

In `.env` set `RAG_NAS_HOST` to the Synology's **LAN IP**, not
`localhost`. The app talks SMB from inside a container, and loopback
there is the container, not the NAS.

Point the mount at the real folder — edit `docker-compose.yml`, in both
`app` and `indexer`:

```yaml
    volumes:
      - /volume1/company:/mnt/nas:ro      # your share name
      - index:/data
```

Then:

```bash
docker compose up -d --build app indexer
```

Note `app indexer` — this deliberately leaves out Caddy, because DSM
already owns ports 80 and 443.

**TLS via DSM.** Control Panel → **Login Portal → Advanced → Reverse
Proxy** → Create.

| Field | Value |
|---|---|
| Source protocol | HTTPS |
| Source hostname | `search.company.local` |
| Source port | 443 |
| Destination protocol | HTTP |
| Destination hostname | `localhost` |
| Destination port | 8501 |

In that entry's **Custom Header** tab, click Create → **WebSocket**.
Streamlit will load and then sit frozen without it.

Issue the certificate under Control Panel → **Security → Certificate**,
and assign it to the reverse proxy entry.

---

## 3b. Install on a separate Linux host

Ubuntu Server 24.04, wired, static IP, on the same VLAN as the NAS.

```bash
sudo apt update && sudo apt install -y docker.io docker-compose-v2 cifs-utils
```

Mount the share read-only:

```bash
sudo install -m 600 /dev/null /root/.smbcred
sudo tee /root/.smbcred >/dev/null <<'EOF'
username=rag-indexer
password=THE-PASSWORD
EOF
```

Add to `/etc/fstab`, as one line:

```
//nas.local/company /mnt/nas cifs ro,credentials=/root/.smbcred,vers=3.1.1,iocharset=utf8,uid=10001,gid=10001,_netdev,x-systemd.automount,nofail 0 0
```

`uid=10001` matches the non-root user inside the container. Then:

```bash
sudo mkdir -p /mnt/nas && sudo mount -a && ls /mnt/nas     # must list your folders
```

Reboot once and check `ls /mnt/nas` again before going further — a mount
that only works until the next power cut is the most common way this
setup fails quietly.

```bash
git clone <your repo url> /opt/rag && cd /opt/rag
cp .env.example .env && vi .env
docker compose --profile standalone-host up -d --build
```

Edit `Caddyfile` first and replace `search.company.local` with the real
hostname.

---

## 4. First run: census before you index

Do not index 50 GB blind. Look at what is there:

```bash
docker compose run --rm indexer python -m indexer --census
```

This walks the share and prints a file count and size per extension. It
reads no file contents and costs nothing. Use it to decide two things:

- **Scanned documents.** A large `.pdf` count with few `.docx` or `.txt`
  files suggests scans. OCR on a big scanned corpus runs for days on CPU.
  Set `RAG_OCR=0` for the first pass, get text documents searchable, and
  turn OCR on afterwards.
- **Language.** If documents are Hindi or Gujarati, set
  `RAG_EMBEDDING_MODEL=BAAI/bge-m3` and add the Tesseract language
  packages to the `Dockerfile` before the first real index. Changing the
  model later means a full rebuild.

Then run the real thing. Expect hours:

```bash
docker compose logs -f indexer
```

Subsequent nights re-read only what changed, so they take minutes.

---

## 5. Name your roster files

Copy `canonical_sources.yaml.example` to `canonical_sources.yaml` and
name the authoritative file for anything countable:

```yaml
sources:
  employees: /mnt/nas/HR/employee_roster.xlsx
```

Without this, "how many employees do we have" is answered from whichever
fragments of the roster happened to be retrieved, which is how a
confident wrong number gets produced. With it, the assistant reads the
whole file and cites it.

---

## 6. Verify before letting anyone in

Sign in as yourself, then as someone with narrower access.

1. **Access is real.** Ask the second account something only HR should
   see. It must answer that it has no information — and the wording must
   be identical to a genuinely unknown question.
2. **Revocation is live.** Remove a user's access to a folder in DSM.
   Without re-indexing, ask them about a document in it. It must
   disappear immediately.
3. **File search works.** Switch to "Find a file" and search for
   something that is an image or a drawing. It should return the path.
4. **Counting works.** Ask "how many employees do we have" and check it
   cites the roster you named.
5. **Nightly index runs.** Edit a file on the share, wait for the next
   night, confirm the change is answerable.
6. **Restore works.** This is the one people skip. Copy the `index`
   volume elsewhere, restore it onto a clean install, confirm queries
   still work. Rebuilding from scratch is hours you will not want to
   spend during an outage.

Check `logs/events.jsonl` in the `index` volume as you go. Each line has
the username, the paths retrieved, latency and cost. Confirm no path
outside a user's access ever appears on their line.

---

## 7. What IT needs to do

- Firewall: app host → NAS on **445**, app host → `api.anthropic.com` on
  **443**, users → app host on **443**. Nothing inbound from the
  internet; remote staff use the existing VPN.
- DNS record for the hostname, and a certificate.
- Deliver the Anthropic API key through a secrets store, not chat or
  email. It goes in `.env`, which is git-ignored.
- Back up the `index` volume weekly, and the `.env` file once.
- Decide with security whether document text may go to the Claude API at
  all. If not, that is a change to a local model, not a setting.

---

## 8. Still to confirm on real hardware

These are written and unit-tested but have never run against a NAS:

- **The ACL pre-filter** (`RAG_ACL_TAGGING`). It needs the Synology to
  answer a security-descriptor query, and it needs group membership to
  resolve through LDAP. Leave it off until both are confirmed. The
  per-file check at query time is correct without it — the pre-filter
  only makes retrieval faster for people with narrow access.
- **The container build.** Docker was not available where this was
  written, so the compose file is valid YAML that has never been built.
  Expect to fix something on the first `docker compose up`.
- **Folder summaries** (`--summaries`). Off by default because it sends
  short excerpts of documents to the Claude API under the indexer's
  account, including from folders individual users cannot read. Approve
  that separately from the content index.
