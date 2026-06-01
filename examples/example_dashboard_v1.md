# Analytics Dashboard

## Problem

Customers have no way to see how their team uses the product. Usage data exists in
our warehouse but is not surfaced anywhere a customer can reach it, so they cannot
judge adoption or justify renewal.

## Requirements

[REQ-001] User can view a dashboard of weekly active users
[REQ-002] User can filter usage charts by date range
[REQ-003] User can export the current chart as a CSV file

## Success Metrics

- 60% of paying accounts open the dashboard within 30 days of launch
- p95 dashboard load time stays under 2 seconds

## Risks

- Warehouse query cost may rise sharply with large accounts