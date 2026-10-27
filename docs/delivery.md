# Delivery slices

These were a dependency chain, not five interchangeable releases. The watcher is shared code;
review and integrate bottom to top. The final operations slice also contains fixes from the
independent cross-cutting review. Do not deploy intermediate slices.

All five lots are merged to `main` (squash merges, in order #2, #12, #6, #8, #10).

| Lot | PR | Base | Behavior |
|---|---|---|---|
| 1 | [#2](https://github.com/amartidandqdq/lg-cinebeam-sonos/pull/2) | main | Startup observation and conservative recovery |
| 2 | [#12](https://github.com/amartidandqdq/lg-cinebeam-sonos/pull/12) | main | Exact route and bounded stability evidence (replaces closed #4) |
| 3 | [#6](https://github.com/amartidandqdq/lg-cinebeam-sonos/pull/6) | main | Focused popup and one opt-in menu fallback |
| 4 | [#8](https://github.com/amartidandqdq/lg-cinebeam-sonos/pull/8) | main | Auth, TLS and destination/size bounds |
| 5 | [#10](https://github.com/amartidandqdq/lg-cinebeam-sonos/pull/10) | main | Controls, operations, CI, review corrections |

The tagged baseline `v0.2.2` resolves to `daf39f76b5349f65b98a5a288ff06ae35b2eac59`.
The candidate is `0.3.0-rc.1`, with no stable 0.3.0 release or hardware deployment claimed.
OpenSpec remains active for outstanding physical validation. See [validation](validation.md)
and [rollback](operations.md).
