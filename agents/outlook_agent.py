"""
Outlook Agent — Sends emails via Microsoft Outlook COM automation.
Requires Outlook to be installed and configured on Windows.
"""

import os
import logging

from agents.base_agent import BaseAgent, AgentResult

logger = logging.getLogger("outlook_agent")


class OutlookAgent(BaseAgent):
    name = "outlook"
    description = "Send emails with attachments via Microsoft Outlook"
    capabilities = ["send_email", "attach_files"]

    def __init__(self):
        self._outlook = None

    def _get_outlook(self):
        """Lazy-load Outlook COM object."""
        if self._outlook is None:
            try:
                import win32com.client
                self._outlook = win32com.client.Dispatch("Outlook.Application")
                logger.info("Outlook COM initialized")
            except ImportError:
                raise RuntimeError(
                    "pywin32 is required for Outlook integration. "
                    "Install with: pip install pywin32"
                )
            except Exception as e:
                raise RuntimeError(
                    f"Cannot connect to Outlook. Is it installed? Error: {e}"
                )
        return self._outlook

    def execute(self, action: str, args: dict) -> AgentResult:
        self._validate_action(action)

        if action == "send_email":
            return self._send_email(**args)
        elif action == "attach_files":
            return self._send_email(**args)  # attach_files is part of send_email

        return AgentResult(success=False, message=f"Unknown action: {action}")

    # ── Actions ──────────────────────────────

    def _send_email(self, to: str, subject: str, body: str,
                    attachments: list | None = None) -> AgentResult:
        """
        Send an email via Outlook COM.
        
        Args:
            to:          Recipient email address (comma-separated for multiple)
            subject:     Email subject line
            body:        Email body text
            attachments: List of file paths to attach
        """
        try:
            outlook = self._get_outlook()

            # Create mail item (0 = olMailItem)
            mail = outlook.CreateItem(0)
            mail.To = to
            mail.Subject = subject
            mail.Body = body

            # Add attachments
            attached_names = []
            if attachments:
                for file_path in attachments:
                    file_path = str(file_path)
                    if os.path.exists(file_path):
                        mail.Attachments.Add(os.path.abspath(file_path))
                        attached_names.append(os.path.basename(file_path))
                        logger.info("Attached: %s", file_path)
                    else:
                        logger.warning("Attachment not found: %s", file_path)

            mail.Send()

            attach_msg = ""
            if attached_names:
                attach_msg = f" with attachments: {', '.join(attached_names)}"

            logger.info("Email sent to: %s", to)
            return AgentResult(
                success=True,
                message=f"✅ Email sent to {to}{attach_msg}",
                data={"to": to, "subject": subject}
            )

        except RuntimeError as e:
            # Outlook not available
            logger.error("Outlook unavailable: %s", e)
            return AgentResult(success=False, message=f"❌ {e}")

        except Exception as e:
            logger.exception("Failed to send email")
            return AgentResult(success=False, message=f"❌ Email error: {e}")
