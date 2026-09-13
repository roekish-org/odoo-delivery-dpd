# Local Odoo 19 demo for the roekish_delivery_dpd module.
DB ?= dpd
COMPOSE = docker compose

.PHONY: build init up down logs shell test reset

build: ## Build the Odoo image (installs roulier)
	$(COMPOSE) build

init: build ## Create the demo database with the module + demo data
	$(COMPOSE) up -d db
	$(COMPOSE) run --rm odoo odoo -c /etc/odoo/odoo.conf -d $(DB) \
		-i roekish_delivery_dpd --without-demo=False --stop-after-init

up: ## Start Odoo -> http://localhost:8069  (login admin / admin)
	$(COMPOSE) up -d
	@echo "Odoo running on http://localhost:8069  (db: $(DB))"

down: ## Stop the stack
	$(COMPOSE) down

logs: ## Follow the Odoo logs
	$(COMPOSE) logs -f odoo

shell: ## Open an Odoo shell on the demo database
	$(COMPOSE) run --rm odoo odoo shell -c /etc/odoo/odoo.conf -d $(DB) --no-http

test: ## Run the module test suite
	$(COMPOSE) run --rm odoo odoo -c /etc/odoo/odoo.conf -d $(DB) \
		-u roekish_delivery_dpd --test-enable --test-tags=/roekish_delivery_dpd \
		--stop-after-init

reset: ## Drop the demo database
	$(COMPOSE) exec -T db dropdb -U odoo --if-exists $(DB)
