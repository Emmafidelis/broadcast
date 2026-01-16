# Copyright (c) 2025, Emanuel Fidelis and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime, get_datetime, flt
from datetime import timedelta


class AdvertisementBroadcast(Document):
	STATUS_TRANSITIONS = {
		"Draft": ["Scheduled", "Cancelled"],
		"Scheduled": ["Aired", "Missed", "Cancelled"],
		"Aired": ["Missed"],  # Allow correction if marked incorrectly
		"Missed": ["Scheduled", "Cancelled", "Aired"],  # Allow reschedule or correction
		"Cancelled": [],  # Terminal state - no transitions allowed
	}

	AUTO_STATUS_TOLERANCE_MINUTES = 10
	def validate(self):
		"""Validate document before saving"""
		self.calculate_total_amount()
		self.validate_schedule()
		self.sync_status_from_context()
		self.validate_status_transition()

		# Handle auto_generate_invoice checkbox functionality

	def before_save(self):
		"""Called before saving document"""
		self.calculate_variance_for_logs()
		self.sync_status_from_context()

		# Handle status transitions
		self.on_status_change()

		# Update notification_sent field based on actual state
		if hasattr(self, '_notification_sent_flag'):
			self.notification_sent = self._notification_sent_flag
		else:
			# Default to 0 since we removed automatic notifications
			self.notification_sent = 0

	def on_submit(self):
		"""Called when document is submitted"""
		if self.status == "Draft":
			self.status = "Scheduled"
		self.sync_status_from_context()
		self.db_set("status", self.status, update_modified=False)
		self.schedule_reminder_notifications()

		# Create Sales Order on submit
		if not self.sales_order:
			self.create_sales_order()

		if self.auto_generate_invoice and self.status == "Aired":
			self.create_sales_invoice()

	def on_cancel(self):
		"""Called when document is cancelled"""
		self.status = "Cancelled"
		self.mark_notification_not_sent()
		self.db_set("status", self.status, update_modified=False)

	def after_insert(self):
		# Removed automatic notifications for better UX
		# Only schedule essential reminders
		self.schedule_reminder_notifications()

	def calculate_total_amount(self):
		"""Calculate total amount based on duration and rate"""
		if self.duration_seconds and self.rate_per_second:
			self.total_amount = flt(self.duration_seconds) * flt(self.rate_per_second)

	def validate_schedule(self):
		"""Validate scheduling constraints"""
		if not self.scheduled_date or not self.scheduled_time:
			return

		scheduled_datetime = get_datetime(
			f"{self.scheduled_date} {self.scheduled_time}"
		)

		if self.is_new():
			if scheduled_datetime < now_datetime():
				frappe.throw(_("Cannot schedule advertisement in the past"))
			return

		old_doc = self.get_doc_before_save()
		if old_doc and (
				old_doc.scheduled_date != self.scheduled_date
				or old_doc.scheduled_time != self.scheduled_time
		):
			if scheduled_datetime < now_datetime():
				frappe.throw(_("Cannot reschedule advertisement to the past"))

	def validate_status_transition(self):
		"""Validate status transitions according to workflow rules"""
		if not self.is_new():
			old_doc = self.get_doc_before_save()
			if old_doc and old_doc.status != self.status:
				self.validate_status_change(old_doc.status, self.status)

	def validate_status_change(self, old_status, new_status):
		"""Validate if status change is allowed"""
		if old_status == new_status:
			return  # No change

		if new_status not in self.STATUS_TRANSITIONS.get(old_status, []):
			frappe.throw(_(
				"Cannot change status from '{0}' to '{1}'. "
				"Allowed transitions from '{0}' are: {2}"
			).format(
				old_status,
				new_status,
				", ".join(self.STATUS_TRANSITIONS.get(old_status, []))
			))

	def on_status_change(self):
		"""Handle actions when status changes"""
		if not self.is_new():
			old_doc = self.get_doc_before_save()
			if old_doc and old_doc.status != self.status:
				self.handle_status_transition(old_doc.status, self.status)

	def handle_status_transition(self, old_status, new_status):
		"""Handle specific actions for status transitions"""
		# Log status change
		self.add_comment("Info", f"Status changed from {old_status} to {new_status}")

		# Handle specific transitions
		if new_status == "Aired" and old_status in {"Scheduled", "Missed"}:
			self.on_aired()
		elif new_status == "Missed" and old_status == "Scheduled":
			self.on_missed()
		elif new_status == "Scheduled" and old_status in {"Missed", "Draft"}:
			self.on_scheduled(previous_status=old_status)
		elif new_status == "Cancelled":
			self.on_cancelled()

	def on_aired(self):
		"""Actions when advertisement is marked as aired"""
		# Auto-generate invoice if enabled and paid
		if self.auto_generate_invoice and not self.sales_invoice:
			try:
				self.create_sales_invoice()
			except Exception as e:
				frappe.log_error(f"Auto-invoice generation failed: {str(e)}", "Advertisement Broadcast")

		# Mark notification as sent (since broadcast completed)
		self.mark_notification_sent()

	def on_missed(self):
		"""Actions when advertisement is marked as missed"""
		# Log the missed broadcast for analytics
		self.add_comment("Warning", f"Advertisement missed at scheduled time: {self.scheduled_date} {self.scheduled_time}")

		# Reset notification status
		self.mark_notification_not_sent()

	def on_scheduled(self, previous_status=None):
		"""Actions when advertisement is scheduled or rescheduled"""
		# Reset notification status for new schedule
		self.mark_notification_not_sent()

		# Schedule new reminder notifications
		self.schedule_reminder_notifications()

	def on_cancelled(self):
		"""Actions when advertisement is cancelled"""
		# Add cancellation comment
		self.add_comment("Info", "Advertisement cancelled")

		# Reset notification status
		self.mark_notification_not_sent()

	def calculate_variance_for_logs(self):
		"""Calculate time variance for broadcast logs"""
		if not self.broadcast_logs:
			return

		scheduled_datetime = get_datetime(
			f"{self.scheduled_date} {self.scheduled_time}"
		)

		for log in self.broadcast_logs:
			if log.actual_broadcast_datetime:
				actual_datetime = get_datetime(log.actual_broadcast_datetime)
				variance = (actual_datetime - scheduled_datetime).total_seconds()
				log.variance_seconds = int(variance)

	@frappe.whitelist()
	def create_sales_order(self):
		"""Create sales order on submit"""
		if self.sales_order:
			return

		try:
			service_item = self.get_or_create_service_item()

			sales_order = frappe.get_doc(
				{
					"doctype": "Sales Order",
					"customer": self.customer,
					"transaction_date": frappe.utils.today(),
					"delivery_date": self.scheduled_date,
					"items": [
						{
							"item_code": service_item,
							"description": f"Advertisement: {self.advertisement_title}",
							"qty": 1,
							"rate": self.total_amount,
							"delivery_date": self.scheduled_date,
						}
					],
					"advertisement_broadcast": self.name,
				}
			)

			sales_order.insert()

			self.sales_order = sales_order.name
			self.payment_status = "Unpaid"
			self.db_set("sales_order", sales_order.name, update_modified=False)
			self.db_set("payment_status", "Unpaid", update_modified=False)

			frappe.msgprint(f"Sales Order {sales_order.name} created successfully", alert=True)

		except Exception as e:
			frappe.log_error(f"Error creating sales order: {str(e)}", "Advertisement Broadcast Sales Order Creation")
			frappe.throw(f"Failed to create sales order: {str(e)}")

	@frappe.whitelist()
	def create_sales_invoice(self):
		"""Auto-generate sales invoice upon successful broadcast"""
		if self.sales_invoice:
			return

		if not self.sales_order:
			frappe.throw(_("Sales Order must be created first"))

		try:
			# Calculate billable amount based on actual broadcasts
			billable_amount = 0
			for log in self.broadcast_logs:
				if log.actual_duration:
					billable_amount += flt(log.actual_duration) * flt(self.rate_per_second)

			if billable_amount == 0:
				billable_amount = self.total_amount

			service_item = self.get_or_create_service_item()

			invoice = frappe.get_doc(
				{
					"doctype": "Sales Invoice",
					"customer": self.customer,
					"posting_date": frappe.utils.today(),
					"items": [
						{
							"item_code": service_item,
							"description": f"Advertisement: {self.advertisement_title}",
							"qty": 1,
							"rate": billable_amount,
							"amount": billable_amount,
							"sales_order": self.sales_order,
						}
					],
					"advertisement_broadcast": self.name,
				}
			)

			invoice.insert()

			self.sales_invoice = invoice.name
			self.db_set("sales_invoice", invoice.name, update_modified=False)
			self.update_payment_status()

			frappe.msgprint(f"Sales Invoice {invoice.name} created successfully", alert=True)

		except Exception as e:
			frappe.log_error(f"Error creating sales invoice: {str(e)}", "Advertisement Broadcast Invoice Creation")
			frappe.throw(f"Failed to create sales invoice: {str(e)}")

	def get_or_create_service_item(self):
		"""Get or create the service item for advertisement broadcast"""
		item_code = "Advertisement Broadcast Service"

		# Check if item exists
		if frappe.db.exists("Item", item_code):
			return item_code

		# Create the service item
		try:
			item = frappe.get_doc({
				"doctype": "Item",
				"item_code": item_code,
				"item_name": "Advertisement Broadcast Service",
				"item_group": "Services",
				"is_service_item": 1,
				"is_sales_item": 1,
				"is_purchase_item": 0,
				"is_stock_item": 0,
				"include_item_in_manufacturing": 0,
				"description": "Service item for advertisement broadcast billing"
			})
			item.insert(ignore_permissions=True)
			frappe.db.commit()
			return item_code

		except Exception as e:
			frappe.log_error(f"Error creating service item: {str(e)}", "Service Item Creation")
			# Fallback to a generic service item or throw error
			frappe.throw(f"Could not create service item: {str(e)}")

		# Invoice notification removed for better UX
		# Invoice will be visible in the document

	def send_scheduling_notification(self):
		"""DEPRECATED: Notification removed for better UX"""
		# This method is kept for backward compatibility but does nothing
		# Notifications were causing poor user experience
		self.notification_sent = 0  # Mark as not sent since we're not sending

	def mark_notification_sent(self):
		"""Mark notification as sent"""
		self._notification_sent_flag = 1
		self.db_set('notification_sent', 1, update_modified=False)

	def mark_notification_not_sent(self):
		"""Mark notification as not sent"""
		self._notification_sent_flag = 0
		self.db_set('notification_sent', 0, update_modified=False)

	def schedule_reminder_notifications(self):
		"""Schedule reminder notifications"""
		if self.docstatus != 1 or self.status != "Scheduled":
			return

		scheduled_datetime = get_datetime(
			f"{self.scheduled_date} {self.scheduled_time}"
		)

		# Schedule 1 hour before reminder
		reminder_time = scheduled_datetime - timedelta(hours=1)
		if reminder_time > now_datetime():
			frappe.enqueue_doc(
				"Advertisement Broadcast",
				self.name,
				"send_reminder_notification",
				queue="short",
				at_time=reminder_time,
			)

	def send_reminder_notification(self):
		"""Send reminder notification before broadcast"""
		frappe.sendmail(
			recipients=[self.presenter],
			subject=f"REMINDER: Advertisement in 1 hour - {self.advertisement_title}",
			message=f"""
			REMINDER: You have an advertisement broadcast in 1 hour!
			
			Advertisement: {self.advertisement_title}
			Customer: {self.customer}
			Scheduled: {self.scheduled_date} at {self.scheduled_time}
			Duration: {self.duration_seconds} seconds
			
			Please prepare for broadcast to avoid missed revenue.
			""",
			reference_doctype="Advertisement Broadcast",
			reference_name=self.name,
		)

	def log_broadcast(
		self,
		actual_datetime,
		actual_duration,
		logged_by,
		broadcast_type="Manual Entry",
		confidence=None,
		notes=None,
	):
		"""Log a broadcast occurrence"""
		log_entry = {
			"actual_broadcast_datetime": actual_datetime,
			"actual_duration": actual_duration,
			"broadcast_type": broadcast_type,
			"logged_by": logged_by,
			"notes": notes or "",
		}

		if confidence:
			log_entry["detection_confidence"] = confidence

		self.append("broadcast_logs", log_entry)

		# Update status based on logs
		if self.docstatus == 1 and self.status != "Cancelled":
			self.status = "Aired"

		self.save()

		# Broadcast confirmation notification removed for better UX
		# Status change is sufficient indication

		# Auto-generate invoice if enabled
		if self.auto_generate_invoice:
			self.create_sales_invoice()

	def send_broadcast_confirmation(self):
		"""DEPRECATED: Confirmation notification removed for better UX"""
		# This method is kept for backward compatibility but does nothing
		# Status updates and dashboard provide sufficient feedback
		pass

	def send_invoice_notification(self, invoice_name):
		"""DEPRECATED: Invoice notification removed for better UX"""
		# This method is kept for backward compatibility but does nothing
		# Invoice will be linked and visible in the document
		pass

	def has_successful_broadcast(self):
		"""Return True if any broadcast log has an actual datetime"""
		return any(
			log.actual_broadcast_datetime for log in (self.broadcast_logs or [])
		)

	def sync_status_from_context(self):
		"""Keep status aligned with document state"""
		if self.docstatus == 0:
			self.status = "Draft"
			return

		if self.status == "Cancelled":
			return

		if self.has_successful_broadcast():
			self.status = "Aired"
			return

		if not self.scheduled_date or not self.scheduled_time:
			return

		scheduled_datetime = get_datetime(
			f"{self.scheduled_date} {self.scheduled_time}"
		)
		tolerance = timedelta(minutes=self.AUTO_STATUS_TOLERANCE_MINUTES)
		current_time = now_datetime()

		if scheduled_datetime + tolerance < current_time:
			self.status = "Missed"
		else:
			self.status = "Scheduled"

	@frappe.whitelist()
	def update_payment_status(self):
		"""Update payment status based on sales invoice"""
		if not self.sales_invoice and self.sales_order:
			self.sales_invoice = self._find_sales_invoice_from_order()
			if self.sales_invoice:
				self.db_set("sales_invoice", self.sales_invoice, update_modified=False)

		if not self.sales_invoice:
			self.payment_status = "Unpaid"
			return

		invoice = frappe.get_doc("Sales Invoice", self.sales_invoice)
		if invoice.status == "Paid":
			self.payment_status = "Paid"
		elif invoice.status == "Overdue":
			self.payment_status = "Overdue"
		elif invoice.outstanding_amount < invoice.grand_total:
			self.payment_status = "Partially Paid"
		else:
			self.payment_status = "Unpaid"

		self.db_set("payment_status", self.payment_status, update_modified=False)

	def _find_sales_invoice_from_order(self):
		"""Find the latest submitted sales invoice linked to the sales order."""
		invoice_items = frappe.get_all(
			"Sales Invoice Item",
			filters={"sales_order": self.sales_order},
			fields=["parent"],
			order_by="creation desc",
		)
		for item in invoice_items:
			doc = frappe.get_doc("Sales Invoice", item.parent)
			if doc.docstatus == 1:
				return doc.name
		return None

	@frappe.whitelist()
	def check_payment_and_autoplay(self):
		"""Check if payment is done and autoplay is allowed"""
		self.update_payment_status()

		if not self.autoplay_enabled:
			return {"allowed": False, "reason": "Autoplay is disabled"}

		if not self.audio_file:
			return {"allowed": False, "reason": "No media file uploaded"}

		if self.payment_status != "Paid":
			return {"allowed": False, "reason": f"Payment not completed. Status: {self.payment_status}"}

		if self.status not in ["Scheduled", "Aired"]:
			return {"allowed": False, "reason": f"Invalid status: {self.status}"}

		return {
			"allowed": True,
			"audio_file": self.audio_file,
			"scheduled_datetime": f"{self.scheduled_date} {self.scheduled_time}",
			"duration": self.duration_seconds,
		}
