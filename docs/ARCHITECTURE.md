# Heriglobal POS System Architecture

## Technology Stack
- **Backend**: Python 3.9+ with Flask
- **Database**: SQLite (Development), PostgreSQL (Production recommended)
- **ORM**: SQLAlchemy
- **Frontend**: Jinja2 Templates, Alpine.js, Tailwind CSS
- **Authentication**: Flask-Login
- **Assets**: Lucide Icons

## Application Structure
```
heriglobal-pos/
├── app.py                  # Application entry point & factory
├── config.py               # Configuration classes
├── models/                 # Database models package
│   ├── __init__.py         # Exports all models
│   ├── user.py
│   ├── outlet.py
│   ├── product.py
│   ├── sale.py
│   ├── ...
├── blueprints/             # Feature modules (Routes & Logic)
│   ├── auth.py
│   ├── dashboard.py
│   ├── admin_dashboard.py
│   ├── pos.py
│   ├── sales.py
│   ├── inventory.py
│   ├── reports.py
│   ├── ...
├── templates/              # HTML Templates
│   ├── base.html           # Layout
│   ├── auth/
│   ├── dashboard/
│   ├── pos/
│   ├── ...
├── static/                 # Static Assets
│   ├── css/
│   ├── js/
│   ├── images/
└── utils/                  # Helper utilities
    ├── decorators.py
    ├── helpers.py
```

## Database Schema Overview
- **Users & Roles**: RBAC system (Super Admin, GM, Outlet Admin, Sales Rep, Accountant).
- **Outlets**: Multi-outlet support with a central Warehouse.
- **Inventory**: Product catalog, stock levels per outlet, transfers, adjustments.
- **Sales**: POS transactions, cart management, payment modes (Cash, Credit, Transfer).
- **Customers**: Customer profiles, credit limits, current balance tracking.
- **Finance**: Repayments, Expenses, Remittances, Cash Collections.

## Key Design Patterns
- **Blueprints**: Modular application design.
- **Factory Pattern**: `create_app` for initialization.
- **Decorators**: `@role_required` for access control.
- **Fat Models**: Business logic encapsulated in models where appropriate.
