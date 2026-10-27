# Delivery slices

These are a dependency chain, not five interchangeable releases. The watcher is shared code;
review and integrate bottom to top. The final operations slice also contains fixes from the
independent cross-cutting review. Do not deploy intermediate slices.

| Lot | PR | Base | Behavior |
|---|---|---|---|
| 1 | [#2](https://github.com/amartidandqdq/lg-cinebeam-sonos/pull/2) | main | Startup observation and conservative recovery |
| 2 | [#4](https://github.com/amartidandqdq/lg-cinebeam-sonos/pull/4) | lot 1 | Exact route and bounded stability evidence |
| 3 | [#6](https://github.com/amartidandqdq/lg-cinebeam-sonos/pull/6) | lot 2 | Focused popup and one opt-in menu fallback |
| 4 | [#8](https://github.com/amartidandqdq/lg-cinebeam-sonos/pull/8) | lot 3 | Auth, TLS and destination/size bounds |
| 5 | [#10](https://github.com/amartidandqdq/lg-cinebeam-sonos/pull/10) | lot 4 | Controls, operations, CI, review corrections |

The tagged baseline `v0.2.2` resolves to `daf39f76b5349f65b98a5a288ff06ae35b2eac59`.
The candidate is `0.3.0-rc.1`, with no stable 0.3.0 release or hardware deployment claimed.
OpenSpec remains active for outstanding physical validation. See [validation](validation.md)
and [rollback](operations.md).
