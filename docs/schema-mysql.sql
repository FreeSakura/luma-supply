
CREATE TABLE index_tasks (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	status VARCHAR(20), 
	reason VARCHAR(200) NOT NULL, 
	attempts INTEGER, 
	error TEXT, 
	created_at DATETIME, 
	PRIMARY KEY (id)
)

;


CREATE TABLE settings (
	`key` VARCHAR(60) NOT NULL, 
	value JSON NOT NULL, 
	PRIMARY KEY (`key`)
)

;


CREATE TABLE users (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	username VARCHAR(40) NOT NULL, 
	phone VARCHAR(30), 
	password_hash VARCHAR(200) NOT NULL, 
	`role` VARCHAR(20) NOT NULL, 
	name VARCHAR(80), 
	permissions JSON, 
	active BOOL, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	UNIQUE (username), 
	UNIQUE (phone)
)

;


CREATE TABLE verifications (
	phone VARCHAR(30) NOT NULL, 
	code_hash VARCHAR(64) NOT NULL, 
	expires_at DATETIME NOT NULL, 
	attempts INTEGER, 
	sent_at DATETIME, 
	PRIMARY KEY (phone)
)

;


CREATE TABLE addresses (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER NOT NULL, 
	recipient VARCHAR(80) NOT NULL, 
	phone VARCHAR(30) NOT NULL, 
	detail VARCHAR(300) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)

;


CREATE TABLE audit_logs (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER, 
	action VARCHAR(80) NOT NULL, 
	target VARCHAR(100) NOT NULL, 
	details JSON, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)

;


CREATE TABLE media (
	id VARCHAR(64) NOT NULL, 
	owner_id INTEGER NOT NULL, 
	purpose VARCHAR(30) NOT NULL, 
	mime VARCHAR(80) NOT NULL, 
	path VARCHAR(300) NOT NULL, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(owner_id) REFERENCES users (id)
)

;


CREATE TABLE merchants (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER NOT NULL, 
	shop_name VARCHAR(100) NOT NULL, 
	legal_name VARCHAR(100), 
	phone VARCHAR(30), 
	address VARCHAR(300), 
	license_media_id VARCHAR(64), 
	status VARCHAR(20), 
	reason VARCHAR(300), 
	PRIMARY KEY (id), 
	UNIQUE (user_id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)

;


CREATE TABLE notifications (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER NOT NULL, 
	message VARCHAR(500) NOT NULL, 
	link VARCHAR(200), 
	`read` BOOL, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)

;


CREATE TABLE orders (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	number VARCHAR(40) NOT NULL, 
	customer_id INTEGER NOT NULL, 
	service_id INTEGER NOT NULL, 
	idempotency_key VARCHAR(100) NOT NULL, 
	request_hash VARCHAR(64) NOT NULL, 
	status VARCHAR(20), 
	version INTEGER, 
	total INTEGER NOT NULL, 
	remark TEXT, 
	delivery_mode VARCHAR(20), 
	address_snapshot JSON, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	UNIQUE (number), 
	FOREIGN KEY(customer_id) REFERENCES users (id), 
	FOREIGN KEY(service_id) REFERENCES users (id), 
	UNIQUE (idempotency_key)
)

;


CREATE TABLE pricing_rules (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	multiplier_bp INTEGER NOT NULL, 
	created_by INTEGER NOT NULL, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
)

;


CREATE TABLE products (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	name VARCHAR(150) NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	category VARCHAR(50) NOT NULL, 
	description TEXT, 
	status VARCHAR(20), 
	owner_id INTEGER, 
	custom BOOL, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(owner_id) REFERENCES users (id)
)

;


CREATE TABLE search_logs (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER, 
	query VARCHAR(500), 
	results JSON, 
	latency_ms INTEGER NOT NULL, 
	model_version VARCHAR(100) NOT NULL, 
	feedback JSON, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)

;


CREATE TABLE sessions (
	token_hash VARCHAR(64) NOT NULL, 
	user_id INTEGER NOT NULL, 
	expires_at DATETIME NOT NULL, 
	PRIMARY KEY (token_hash), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)

;


CREATE TABLE inquiries (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER NOT NULL, 
	items JSON NOT NULL, 
	message TEXT, 
	status VARCHAR(20), 
	order_id INTEGER, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(order_id) REFERENCES orders (id)
)

;


CREATE TABLE procurements (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	order_id INTEGER NOT NULL, 
	status VARCHAR(30), 
	plan JSON, 
	constraints JSON, 
	planned_at DATETIME, 
	proof_media_ids JSON, 
	version INTEGER, 
	PRIMARY KEY (id), 
	UNIQUE (order_id), 
	FOREIGN KEY(order_id) REFERENCES orders (id)
)

;


CREATE TABLE product_changes (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	product_id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	payload JSON NOT NULL, 
	status VARCHAR(20), 
	reason VARCHAR(300), 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(product_id) REFERENCES products (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)

;


CREATE TABLE shipments (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	order_id INTEGER NOT NULL, 
	idempotency_key VARCHAR(100) NOT NULL, 
	tracking VARCHAR(100), 
	carrier VARCHAR(80), 
	items JSON NOT NULL, 
	proof_media_ids JSON, 
	received BOOL, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(order_id) REFERENCES orders (id), 
	UNIQUE (idempotency_key)
)

;


CREATE TABLE skus (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	product_id INTEGER NOT NULL, 
	code VARCHAR(80) NOT NULL, 
	color VARCHAR(40), 
	size_mm VARCHAR(80), 
	specification VARCHAR(150), 
	unit VARCHAR(20), 
	attributes JSON, 
	images JSON, 
	initial_price INTEGER NOT NULL, 
	manual_price INTEGER, 
	stock_status VARCHAR(20), 
	status VARCHAR(20), 
	PRIMARY KEY (id), 
	FOREIGN KEY(product_id) REFERENCES products (id), 
	UNIQUE (code)
)

;


CREATE TABLE order_lines (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	order_id INTEGER NOT NULL, 
	sku_id INTEGER NOT NULL, 
	quantity INTEGER NOT NULL, 
	unit_price INTEGER NOT NULL, 
	snapshot JSON NOT NULL, 
	shipped_quantity INTEGER, 
	PRIMARY KEY (id), 
	UNIQUE (order_id, sku_id), 
	FOREIGN KEY(order_id) REFERENCES orders (id), 
	FOREIGN KEY(sku_id) REFERENCES skus (id)
)

;


CREATE TABLE quotes (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	merchant_id INTEGER NOT NULL, 
	sku_id INTEGER NOT NULL, 
	version INTEGER NOT NULL, 
	price INTEGER NOT NULL, 
	available_quantity INTEGER, 
	reserved_quantity INTEGER, 
	min_quantity INTEGER, 
	lead_days INTEGER, 
	freight INTEGER, 
	valid_until DATETIME NOT NULL, 
	status VARCHAR(20), 
	active BOOL, 
	deleted BOOL, 
	reason VARCHAR(300), 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	UNIQUE (merchant_id, sku_id, version), 
	FOREIGN KEY(merchant_id) REFERENCES merchants (id), 
	FOREIGN KEY(sku_id) REFERENCES skus (id)
)

;


CREATE TABLE reviews (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	order_id INTEGER NOT NULL, 
	sku_id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	text TEXT NOT NULL, 
	media_ids JSON, 
	reply TEXT, 
	deleted BOOL, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	UNIQUE (order_id, sku_id, user_id), 
	FOREIGN KEY(order_id) REFERENCES orders (id), 
	FOREIGN KEY(sku_id) REFERENCES skus (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)

;


CREATE TABLE wishlist (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER NOT NULL, 
	sku_id INTEGER NOT NULL, 
	room VARCHAR(60), 
	quantity INTEGER, 
	note VARCHAR(300), 
	watch_price BOOL, 
	watch_stock BOOL, 
	PRIMARY KEY (id), 
	UNIQUE (user_id, sku_id, room), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(sku_id) REFERENCES skus (id)
)

;


CREATE TABLE tickets (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	order_id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	line_id INTEGER NOT NULL, 
	quantity INTEGER NOT NULL, 
	category VARCHAR(40) NOT NULL, 
	description TEXT NOT NULL, 
	media_ids JSON, 
	status VARCHAR(20), 
	history JSON, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(order_id) REFERENCES orders (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(line_id) REFERENCES order_lines (id)
)

;