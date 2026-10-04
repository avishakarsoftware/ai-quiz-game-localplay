# October 2026 production rollout evidence

Updated 2026-10-04 UTC (2026-10-03 PDT). **Preparation; production unchanged.**

Avi authorized plan review, fixes, commit/push and rollout through production, with rollback
readiness and protection of the shared database. Codex operates and reviews the release, with
independent reviewers. The separate Revelry repository push was rejected by automatic approval
review as outside the interpreted scope; explicit approval for that narrow publication and
consumer rollout is pending. See [promotion plan](PROD-ROLLOUT-2026-10.md).

## Frozen artifacts

| Component | Identity |
|---|---|
| LocalPlay runtime | `0bf942094a2e9e6bc6680b4a49b430834cf0cb84` |
| Exact gamma / proposed production image | `sha256:394e8061a2923cb295bc02566a4884facdcadfcefc4fb17a287cb3be90e57051` |
| Required CI | [37160187919](https://github.com/avishakarsoftware/ai-quiz-game-localplay/actions/runs/37160187919), all five jobs rechecked green |
| Frozen IONOS archive | SHA-256 `cb53d7d7f1a67e2b67dd0c9e4c21c88d8e62ce67e020c6a67bc55cdfd96c846b` |
| Website JS entry | `index-BxJjwpMz.js`, SHA-256 `6c91763235dd6afb5e73612e5e5244a3e81f221131ca1ee8c96e6ec4a7ebb1af` |
| Original live config retained | SHA-256 `7dc9a682d90e2f01e68e6e5975ec1d75e1432cb88662e348366a734b18cda700` |
| Revelry gamma maintenance commit | `ada6f6e92170c87c3c3b1865409d21dd79c58531`, based on live `06df3136`; not yet pushed |
| Revelry production maintenance commit | `f4497edb1bf42837c5fb9e82a0bd4a1a451a1079`, based on live `e8b97eca`; not yet pushed |
| Consumer maintenance patch | SHA-256 `91c6dc94789c017db4bec996965b31dc4395d389ba2a6d4d675261f579befd18` |

The IONOS build uses a clean runtime archive, explicit existing production Google/Apple and
Cast inputs, Bingo build support, the existing public analytics project key, and the exact
original live config. There is no gamma API URL in its main bundle. Consumer images will copy
only `/app/app/games/service.py` onto their distinct existing immutable bases; production's
older frontend, dependencies and schema assumptions stay intact. The adjacent dirty Revelry
checkout and master were not changed.

## Recovery and shared databases

Private durable VM package: `/home/revelry-games/release-backups/20261004T0350Z/`.
Private IONOS package: `~/localplay-release-backups/20261004T0350Z/`; parent denies web access.
Operator working evidence: `/tmp/localplay-prod-rc-20261004T0350Z/`, mode 700; secret/data files
mode 600. Database capture archives were copied to the private VM package and their hashes
read back. Temporary local working files are not the only recovery copies.

| Backup | SHA-256 / verification |
|---|---|
| Previous LocalPlay image | `sha256:7b328e823c246c5d75627d21c5e67cc2ea8536190f8d933f6c0ffa7960ac7e5e`; retained tag + export |
| Image export | `235e614fbf23bc2ff62f210aa0c48ba927f646a8824a3c65817246010d3bc13b` |
| Private production env | `c41b64b8d1a9f6f5096532338539a771e9e9cfc0b891e6599ee3f6913ff788c7` |
| Mounted-volume snapshot | `0bed8c4211a56e8371fbfd45690ca5f0fedbed5c3fcdd4795de48fe9b1ecddc9` |
| Previous public site | `d47665f9342755b97e9bdc09efea58cde53e39ea31b65621db09081ef67bf983`; index/config/referenced assets verified |
| LocalPlay shared project `hosbtyylacluziugwjfd`, full | `25d89f7882878f15a5a96a66be578da2cfdd02471677e22c62137e9597ab2af0`; 465 tables restored and counts matched |
| LocalPlay focused capture | `08d90c1cab3bdd01659733ed9d9d910f4b307f9651718bfac39417bdd417883f`; four production wallet/ledger/quiz tables' contents matched |
| Revelry shared project `guecgpkuvpwplwmfcqzs`, full | `1ff7385d2c1980b99f4eeb9fb7f75ab07be8b7be19235841217ce77f663feeea`; 184 tables / 5,622 rows restored |
| Revelry focused capture | `ea119b2198df06c769e7b169f4c8723a4497736be3b768bb25aa3ab90592e4ab`; eight production/gamma writer tables plus FK ancestors restored |

Both captures use one exported repeatable-read, read-only snapshot, full and focused dumps,
verified TLS, and no parallel dump workers. Only temporary provider-issued read-only backup
credentials were provisioned; unrelated roles/memberships stayed unchanged. Credential expiry
was not extended while the source snapshot was open. Both restore destinations had no network,
no published ports and no source credentials. Original constraints, including NOT VALID state,
and focused contents matched. Matching the source database owner and search_path in the
isolated rehearsals fixed verification fidelity without changing the live databases.

Exact two production RPC files and original verification SQL passed offline as the source
owner. Only `games_merge_wallet` and `games_save_quiz_pack` metadata changed; all 465 restored
tables retained identical contents, including gamma and other applications. Both RPCs grant
execute only to service_role, with anon/authenticated refused. Verification rows cleaned up;
ledger sequence allocation advanced. Live targeted SQL remains pending.

Backend rollback check passed. Execute rollback with the captured immutable old image, current
volume and existing env; never rewind room snapshots or the shared database. Compatible RPC
hardening stays applied by default. Private old-definition/owner/ACL recovery SQL exists for a
demonstrated function regression. IONOS recovery restores stable files and publishes the old
entry last while retaining both asset sets. Original Cloud Run traffic/config snapshots are saved
for separate consumer rollback.

The unlabeled old LocalPlay image has mixed provenance: live main.py matches `1179b530`, while
socket_manager.py matches `40b8dd09`. Its captured image is the recovery authority.

## Qualification so far

- LocalPlay exact-source CI: all five jobs green; fresh gamma API regression: 64 passed, zero failed.
- Revelry final exact-baseline full no-network suites: gamma 2,904 passed / one skipped;
  production 2,700 passed / three skipped; 241 deselected integration tests in each. Independent
  final focused review: 111 passed on each baseline. Counts overlap and must not be summed.
- The unchanged 86-item unit fixture previously made 172 calls per refresh; the fixed fixture
  makes one bounded read and zero writes, preserving IDs and timestamps. Same-second polling,
  callback, authoring, version, lock and deletion races are covered. Live latency/embedded
  acceptance still pending.
- First gamma restart recovered lobby seats and answered quiz tokens, exact score and answered
  flags. Its initial billing assertion incorrectly assumed a paid start during free-party grace;
  current balance remained unchanged. The corrected full drill passed: lobby/quiz token recovery, answered flags, exact score 999,
  invalid-token refusal, unchanged balance/grace usage and both owned rooms cleaned. A separate retry
  hit one external WebSocket handshake timeout and successfully cleaned its owned rooms;
  shared VM resources and local gamma health were normal.
- npm audit findings were reviewed against actual browser paths. No demonstrated runtime release
  blocker; Node/native-tool findings do not run as web servers. Current public PostHog tours and
  surveys are empty. Upgrade/qualify DOMPurify/PostHog before enabling HTML tours.

The 15-minute pre-window monitor recorded 112 checks. Two isolated timeouts occurred: one
Revelry production probe at the 10-second client timeout, and one gamma probe during the planned
restart. Neither repeated consecutively; no Cloud Run ERROR events were found in the captured
pre-window hour. VM containers remained below 1% CPU and approximately 101/40 MiB RAM.

## Pending production acceptance

The baseline, exact consumer images/live scale gate, targeted live functions, image swap,
publication, owned QA acceptance and attended observation are not complete. Record each actual
result here before marking production deployed. Keep existing feature policy and identities;
no customer-card charges, native/store rollout, broad load or unbudgeted LLM generation.
Successful actual OAuth sign-in, camera/Cast, installed native return, and real payment/refund
remain manual provider/device checks; synthetic guards do not establish those outcomes.
