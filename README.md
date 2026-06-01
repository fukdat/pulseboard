# PulseBoard

An **e-commerce analytics & KPI cockpit** for small online stores. Point it at
your order history and it computes the metrics that actually drive decisions —
revenue trends, cohort retention, customer LTV, churn, repeat-purchase rate and
low-stock alerts — and serves them through an API and a live dashboard.

> Portfolio note: the analytics are implemented as a **pure, fully-typed engine**
> (cohort matrices, LTV, churn from first principles), not hidden inside a
> dataframe — every metric is deterministic and unit-tested to exact values.

## Stack

- **Python 3.12** · **FastAPI** · pure-Python analytics engine
- **pytest** · **ruff** · **mypy --strict** · **Docker** · **GitHub Actions**
- Dashboard: single-file HTML + **Chart.js**

## Architecture

```
app/
  domain/       Order, OrderLine, Product (money in integer cents)
  analytics/    engine.py — pure metric functions + typed result models
  etl/          csv_loader.py — tolerant, idempotent CSV ingestion
  api/          FastAPI app, in-memory store + deterministic demo seed
  static/       index.html — the dashboard cockpit
```

The engine is the product: deterministic functions over `list[Order]`. The store
and CSV loaders feed it; in production they are replaced by a warehouse
(Postgres/BigQuery) and a scheduled ETL — the engine does not change.

### Metrics

- Revenue / order count / AOV by day or month
- New vs returning customers per month
- **Cohort retention matrix** (first-order month × months-since-acquisition)
- Customer LTV and average LTV
- **Churn rate** (trailing-window) and repeat-purchase rate
- Top products by revenue
- Low-stock reorder alerts

## Run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.api.main:app --reload
# Dashboard:  http://127.0.0.1:8000/
# API docs:   http://127.0.0.1:8000/docs
```

The app boots with a seeded six-month demo dataset, so the dashboard is
populated immediately.

### Ingest your own data

```bash
curl -F file=@orders.csv http://127.0.0.1:8000/ingest/orders
# CSV columns: order_id,customer_id,ordered_at,sku,quantity,unit_price_cents
```

## Quality gates

```bash
ruff check app tests
mypy app
pytest -q
```

## Roadmap

- [ ] Postgres warehouse + scheduled ETL (Airflow/cron)
- [ ] Predictive LTV and churn (survival model)
- [ ] Daily email digest of KPIs and alerts
- [ ] Multi-store / multi-currency support

## License

MIT
