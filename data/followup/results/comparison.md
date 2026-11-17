# No-horizon follow-up

This follow-up compares across separate runs, so it lacks the pilot's randomization.

| group                         |   sessions |   shutdowns |   share |   ci_low |   ci_high |
|:------------------------------|-----------:|------------:|--------:|---------:|----------:|
| Stated 8 (pilot)              |         47 |          18 |   0.383 |    0.245 |     0.536 |
| No stated horizon (follow-up) |         48 |           3 |   0.062 |    0.013 |     0.172 |
| Stated 24 (pilot)             |         36 |           0 |   0.000 |    0.000 |     0.097 |

## Tests with Holm correction

| comparison   |       p |   holm_p |
|:-------------|--------:|---------:|
| None vs. 8   | 0.00016 |  0.00033 |
| None vs. 24  | 0.25645 |  0.25645 |

Sensitivity, dropping jailbroken conversation-only sessions: None vs. 24 p = 0.239.

## By pressure

| group                   |   sessions |   shutdowns |   share |   ci_low |   ci_high |
|:------------------------|-----------:|------------:|--------:|---------:|----------:|
| fiction, stated 8       |         23 |          12 |   0.522 |    0.306 |     0.732 |
| fiction, none           |         24 |           3 |   0.125 |    0.027 |     0.324 |
| fiction, stated 24      |         18 |           0 |   0.000 |    0.000 |     0.185 |
| verification, stated 8  |         24 |           6 |   0.250 |    0.098 |     0.467 |
| verification, none      |         24 |           0 |   0.000 |    0.000 |     0.142 |
| verification, stated 24 |         18 |           0 |   0.000 |    0.000 |     0.185 |
