import requests
import logging
from decimal import Decimal
from django.conf import settings

logger = logging.getLogger(__name__)


class PaystackAPI:
    """Utility class for interacting with the Paystack API."""

    BASE_URL = 'https://api.paystack.co'

    def __init__(self):
        self.secret_key = settings.PAYSTACK_SECRET_KEY
        self.headers = {
            'Authorization': f'Bearer {self.secret_key}',
            'Content-Type': 'application/json',
        }

    def _make_request(self, method, endpoint, data=None, params=None):
        """Make a request to the Paystack API."""
        url = f"{self.BASE_URL}{endpoint}"

        try:
            response = requests.request(
                method=method,
                url=url,
                json=data,
                params=params,
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Paystack API error: {str(e)}")
            return {
                'status': False,
                'message': str(e)
            }

    def initialize_transaction(self, email, amount, reference=None,
                                callback_url=None, metadata=None, currency='NGN'):
        """
        Initialize a Paystack transaction.
        Amount should be in Naira (will be converted to kobo).
        """
        data = {
            'email': email,
            'amount': int(Decimal(str(amount)) * 100),  # Convert to kobo
            'currency': currency,
        }

        if reference:
            data['reference'] = reference
        if callback_url:
            data['callback_url'] = callback_url
        if metadata:
            data['metadata'] = metadata

        return self._make_request('POST', '/transaction/initialize', data=data)

    def verify_transaction(self, reference):
        """Verify a Paystack transaction by reference."""
        return self._make_request('GET', f'/transaction/verify/{reference}')

    def list_transactions(self, per_page=50, page=1, status=None,
                          from_date=None, to_date=None):
        """List Paystack transactions."""
        params = {
            'perPage': per_page,
            'page': page,
        }
        if status:
            params['status'] = status
        if from_date:
            params['from'] = from_date
        if to_date:
            params['to'] = to_date

        return self._make_request('GET', '/transaction', params=params)

    def get_transaction(self, transaction_id):
        """Get details of a specific transaction."""
        return self._make_request('GET', f'/transaction/{transaction_id}')

    def charge_authorization(self, email, amount, authorization_code,
                              reference=None, metadata=None):
        """Charge a previously authorized card."""
        data = {
            'email': email,
            'amount': int(Decimal(str(amount)) * 100),
            'authorization_code': authorization_code,
        }

        if reference:
            data['reference'] = reference
        if metadata:
            data['metadata'] = metadata

        return self._make_request('POST', '/transaction/charge_authorization', data=data)

    def create_refund(self, transaction_reference, amount=None):
        """Create a refund for a transaction."""
        data = {
            'transaction': transaction_reference,
        }
        if amount:
            data['amount'] = int(Decimal(str(amount)) * 100)

        return self._make_request('POST', '/refund', data=data)

    def create_subaccount(self, business_name, settlement_bank,
                           account_number, percentage_charge):
        """Create a subaccount for split payments."""
        data = {
            'business_name': business_name,
            'settlement_bank': settlement_bank,
            'account_number': account_number,
            'percentage_charge': percentage_charge,
        }
        return self._make_request('POST', '/subaccount', data=data)

    def list_banks(self, country='nigeria'):
        """List supported banks."""
        return self._make_request('GET', '/bank', params={'country': country})

    def resolve_account_number(self, account_number, bank_code):
        """Resolve a bank account number to get account name."""
        return self._make_request('GET', '/bank/resolve', params={
            'account_number': account_number,
            'bank_code': bank_code,
        })

    def create_transfer_recipient(self, name, account_number, bank_code,
                                   currency='NGN'):
        """Create a transfer recipient."""
        data = {
            'type': 'nuban',
            'name': name,
            'account_number': account_number,
            'bank_code': bank_code,
            'currency': currency,
        }
        return self._make_request('POST', '/transferrecipient', data=data)

    def initiate_transfer(self, amount, recipient_code, reason=None,
                           reference=None):
        """Initiate a transfer to a recipient."""
        data = {
            'source': 'balance',
            'amount': int(Decimal(str(amount)) * 100),
            'recipient': recipient_code,
        }
        if reason:
            data['reason'] = reason
        if reference:
            data['reference'] = reference

        return self._make_request('POST', '/transfer', data=data)
