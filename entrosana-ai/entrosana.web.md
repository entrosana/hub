# entrosana.com — web hosting setup

**Status:** LIVE on HTTPS (2026-07-23). `https://entrosana.com` + `https://www.entrosana.com`
serve the e14-hosted site through a Cloudflare Tunnel. Host: **e14** (`e14-1`, tailnet `100.115.236.97`).

Migrated off AWS EC2 (`3.64.28.14`, sources in `~/entrosana-from-ec2/`) to self-hosting on e14.

## Public request path
```
visitor ──HTTPS──▶ Cloudflare edge ──▶ Cloudflare Tunnel ──outbound──▶ e14 cloudflared ──▶ http://localhost:4321
         (TLS terminated at CF)        (69e77bd9…cfargotunnel.com)      (entrosana-tunnel.service)   (entrosana-site.service, Node/sirv)
```
- **TLS:** Cloudflare Universal SSL (issuer *Google Trust Services*, CN `entrosana.com`, exp 2026-10-20). Origin link is the encrypted tunnel — the origin never terminates public TLS.
- **Why a tunnel:** e14's uplink is **CGNAT** (Sunrise mobile, public IP `194.230.147.22` behind UMR router `192.168.105.1`). Inbound port-forward is impossible, so the tunnel dials **outbound** to Cloudflare. Home IP is never exposed.

## DNS (Cloudflare)
- **Registrar:** Metanet (holds the NS delegation). **DNS host:** Cloudflare. **Zone id:** `12dc45351e424754da536acca0920950`.
- **Nameservers:** `alexandra.ns.cloudflare.com`, `matias.ns.cloudflare.com` (was GoDaddy `ns03/ns04.domaincontrol.com`). DNSSEC: off.
- **Records:**
  | Name | Type | Value | Proxied |
  |---|---|---|---|
  | `entrosana.com` | CNAME | `69e77bd9-70aa-4d0e-b8ea-16eacc25cb3a.cfargotunnel.com` | yes |
  | `www.entrosana.com` | CNAME | same tunnel | yes |
  | `entrosana.com` | MX | `10 mail.protonmail.ch`, `20 mailsec.protonmail.ch` | — |
  | `entrosana.com` | TXT | `v=spf1 include:_spf.protonmail.ch ~all` | — |
  | `entrosana.com` | TXT | `protonmail-verification=…` | — |
- **Email:** Proton Mail (being set up fresh — replace MX/SPF/verification + the 3 `*._domainkey` DKIM CNAMEs with the new Proton values).

## Cloudflare Tunnel
- **Tunnel:** name `entrosana`, id `69e77bd9-70aa-4d0e-b8ea-16eacc25cb3a`.
- **Config:** `~/.cloudflared/config.yml` — ingress `entrosana.com` + `www.entrosana.com` → `http://localhost:4321`, fallback `http_status:404`.
- **Creds:** `~/.cloudflared/69e77bd9-….json`; account cert `~/.cloudflared/cert.pem`.
- **Service:** `entrosana-tunnel.service` (systemd **--user** unit, linger on) → `cloudflared tunnel --config ~/.cloudflared/config.yml --no-autoupdate run entrosana`. Restart=on-failure.
- **Bring-up script:** `~/entrosana-site/deploy/tunnel/setup-tunnel.sh` (idempotent).

## e14 services (systemd)
| Unit | Role | Port |
|---|---|---|
| `entrosana-site.service` | static marketing site (Node/sirv) — the origin | `:4321` |
| `entrosana-tunnel.service` (--user) | Cloudflare Tunnel → origin (public path) | — |
| `entrosana-edge.service` → `entrosana-edge` (Caddy docker) | LAN TLS edge, local cert, reverse_proxy → :4321 | `192.168.105.119:443` |
| `entrosana-auth.service` | password-gate auth backend | — |
| `entrosana-watcher.service` | security-event watcher for entrosana.com | — |

Source: `~/entrosana-site/` (site + `deploy/`), `~/entrosana-ai/`, `~/entrosana-from-ec2/`.

## Internal / LAN access (split-horizon)
e14's unbound (`/etc/unbound/unbound.conf.d/e14-resolver.conf`) **redirects `entrosana.com` → the tailnet IP**
(`100.115.236.97` / `fd7a:115c:a1e0::2e33:ec61`) for devices on the tailnet. So **tailnet devices (incl. gtaura)
reach the internal path, not the public Cloudflare one.** To test the *public* site, use a device off the tailnet.
The LAN Caddy edge (`entrosana-edge`, `192.168.105.119:443`, local cert → :4321) is the direct-LAN path.
To make tailnet devices use the public path instead, remove the unbound `entrosana.com` redirect block.

## Operations
```bash
# public health (bypass e14 split-horizon)
curl -s --resolve entrosana.com:443:104.21.61.23 -o /dev/null -w '%{http_code}\n' https://entrosana.com/
# tunnel
systemctl --user status entrosana-tunnel.service
cloudflared tunnel info entrosana
# origin site
systemctl --user is-active entrosana-site.service   # (adjust scope if it is a system unit)
# restart tunnel
systemctl --user restart entrosana-tunnel.service
```
- Kill public exposure fast: `systemctl --user stop entrosana-tunnel.service` (site drops offline; DNS unchanged).
- Change what's served: edit `~/.cloudflared/config.yml` ingress, then restart the tunnel service.

## Security notes
- Origin is **outbound-only** — no inbound ports open, home IP hidden behind Cloudflare. (Cloudflare's "allow only CF IPs at origin" step is N/A — nothing is exposed.)
- The `entrosana-auth` gate + `entrosana-watcher` remain in the stack.
- Cloudflare API token used for the DNS cutover was scoped **DNS-edit only** (SSL API returned 403) — revoke after.
- TODO: enable **Always Use HTTPS** (Cloudflare → SSL/TLS → Edge Certificates) for http→https redirect.

---
*Cutover performed 2026-07-23 (Claude, on e14). AWS→e14 via Cloudflare Tunnel; CGNAT-proof; email preserved on Proton.*
