The backup container mounts this directory as /ssh (copied into root's ~/.ssh at container start) (read-only). It needs:

- `id_ed25519`: the key the storage box accepts (both OpenSSH and RFC4716 forms must be in the box's
  `.ssh/authorized_keys`; port 22 insists on RFC4716, port 23 takes either)
- `config`: `Host braize` → `HostName u687114.your-storagebox.de`, `User u687114-sub1`, `Port 23`, `IdentityFile ~/.ssh/id_ed25519`
- `known_hosts`: `ssh-keyscan -p 23 u687114.your-storagebox.de`

Nothing here is committed; the files live on the host.
