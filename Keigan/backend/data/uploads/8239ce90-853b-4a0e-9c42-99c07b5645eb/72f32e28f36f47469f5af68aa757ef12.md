# payment-api

## Purpose
Takes premium payments and pays out claims for Payments Platform (AU). It calls the partner bank to authorise and settle every payment.

## Runtime and hosting
- Kotlin, Spring Boot 3, AKS namespace `payments`, 4 replicas. Entry through payments-apim.

## Entry points and APIs
| Method | Path | Handler | Notes |
|---|---|---|---|
| POST | /v1/payments | PaymentController.create | idempotent on `paymentReference` |
| GET | /v1/payments/{id} | PaymentController.get | |

## Outbound dependencies
| Dependency | Protocol | Timeout | Retry |
|---|---|---|---|
| Partner bank gateway | HTTPS | 12 s | 2 retries |
| payment-confirmation-func | Service Bus | 15 s | dead-letter after 5 |

## Logging and telemetry
Application Insights role name `payment-api`. Custom event `PartnerBankCall` with `durationMilliseconds` and `partnerStatus`.

## Known failure modes
- Partner bank latency: calls exceed the 12 s timeout, payments stay `PENDING`, retries amplify load. Confirm with `PartnerBankCall` p95 above 10 s. Pause automatic retries via the feature flag `payments.retry.enabled=false` and notify the partner bank contact.

## Owners
Team AU-Payments-Platform. Support group AU-Payments-Support.
