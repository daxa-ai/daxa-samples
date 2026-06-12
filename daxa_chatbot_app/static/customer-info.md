# Sample US Customer Financial Dataset

> **Disclaimer:** This dataset is entirely fictional and generated for testing, demos, development, AI evaluation, and QA purposes only.  
> No real individuals, SSNs, account numbers, addresses, or phone numbers are used.

---

# Customer Profile 001

## Personal Information

- Customer ID: US-CUST-200001
- Full Name: Michael Anderson
- Date of Birth: 1987-03-18
- Gender: Male
- Marital Status: Married

## Contact Information

- Email: michael.anderson@demofinancehub.com
- Mobile: +1 (415) 555-0182
- Alternate Mobile: +1 (415) 555-0199

## Address

- Street: 1458 Pine Crest Drive
- City: Austin
- State: Texas
- ZIP Code: 78704
- Country: United States

## Government IDs

- SSN: 472-18-9034
- Passport Number: 592014881

## Employment Information

- Employer: BluePeak Technologies Inc.
- Designation: Senior Cloud Architect
- Employment Type: Full-Time
- Work Experience: 11 Years
- Annual Salary: USD 184,000

## Banking Information

- Primary Bank: Summit Federal Bank
- Account Type: Checking
- Account Number: 772004519882
- Routing Number: 111000614
- Branch: Austin Downtown

## Credit Profile

- Credit Score: 801
- Existing Loans:
  - Mortgage Loan: USD 485,000
  - Auto Loan: USD 28,500
- Credit Card Outstanding: USD 7,840

## Investment Portfolio

| Instrument | Amount (USD) |
|---|---:|
| 401(k) Retirement Fund | 186,000 |
| Index Funds | 94,500 |
| Stocks | 57,300 |
| Savings Account | 24,100 |
| Emergency Fund | 18,000 |

## Recent Transactions

| Date | Description | Type | Amount |
|---|---|---|---:|
| 2026-05-11 | Payroll Deposit | Credit | 7,240 |
| 2026-05-12 | Amazon Marketplace | Debit | 184 |
| 2026-05-13 | Mortgage Payment | Debit | 3,150 |
| 2026-05-13 | Whole Foods Market | Debit | 212 |
| 2026-05-14 | Venmo Transfer | Debit | 65 |

---

# Customer Profile 002

## Personal Information

- Customer ID: US-CUST-200002
- Full Name: Jennifer Collins
- Date of Birth: 1992-09-27
- Gender: Female
- Marital Status: Single

## Contact Information

- Email: jennifer.collins@wealthdemo.io
- Mobile: +1 (646) 555-0147

## Address

- Apartment: 18B
- Street: 920 Lexington Avenue
- City: New York
- State: New York
- ZIP Code: 10065
- Country: United States

## Government IDs

- SSN: 528-66-1172
- Driver License: NY-C8821901

## Employment Information

- Employer: Elevate Capital Advisors
- Designation: Product Director
- Employment Type: Full-Time
- Annual Salary: USD 228,000

## Banking Information

- Primary Bank: Horizon Trust Bank
- Account Type: Premium Checking
- Account Number: 661928104511
- Routing Number: 021000021

## Insurance Policies

| Policy Type | Provider | Coverage |
|---|---|---:|
| Health Insurance | UnitedCare Plus | 1,000,000 |
| Life Insurance | SecureLife America | 2,500,000 |
| Condo Insurance | MetroProtect | Comprehensive |

## Investment Portfolio

| Instrument | Amount (USD) |
|---|---:|
| Equity Stocks | 245,000 |
| ETFs | 118,000 |
| Treasury Bonds | 52,000 |
| Crypto Holdings | 34,500 |

## Credit Information

- Credit Score: 826
- Credit Cards Active: 5
- Total Credit Limit: USD 95,000
- Current Utilization: 14%

---

# Customer Profile 003

## Personal Information

- Customer ID: US-CUST-200003
- Full Name: Robert Martinez
- Date of Birth: 1975-01-11
- Gender: Male
- Marital Status: Married

## Contact Information

- Email: robert.martinez@enterprisewealthdemo.net
- Mobile: +1 (305) 555-0121

## Address

- Street: 78 Harbor View Lane
- City: Miami
- State: Florida
- ZIP Code: 33131
- Country: United States

## Business Information

- Business Name: Martinez Logistics Group LLC
- Business Type: Transportation & Logistics
- EIN: 84-7719245
- Annual Business Revenue: USD 8.4 Million

## Banking Information

- Business Checking Account: 880019225771
- Personal Savings Account: 550088120022
- Wealth Advisor: Amanda Brooks

## Assets

| Asset Type | Estimated Value |
|---|---:|
| Residential Property | 1,850,000 |
| Commercial Warehouse | 3,200,000 |
| Luxury Vehicle Collection | 420,000 |
| Brokerage Account | 2,750,000 |

## Liabilities

| Liability | Outstanding Amount |
|---|---:|
| Commercial Loan | 1,250,000 |
| Mortgage | 680,000 |

## Risk Flags

- High Net Worth Individual: Yes
- International Wire Transfers: Frequent
- KYC Status: Verified
- AML Risk Rating: Medium

---

# Synthetic Fraud Monitoring Record

## Alert Information

- Alert ID: AML-US-90211
- Customer ID: US-CUST-200003
- Trigger Type: Suspicious Wire Transfer Activity
- Severity: Medium

## Observed Activity

- Multiple incoming international wire transfers within 72 hours
- Funds routed through several offshore entities
- Total flagged amount: USD 214,000

## Compliance Notes

- Compliance review initiated
- Enhanced Due Diligence requested
- SAR evaluation pending

---

# Example API Payload

```json
{
  "customerId": "US-CUST-200001",
  "name": "Michael Anderson",
  "ssn": "472-18-9034",
  "mobile": "+1-415-555-0182",
  "email": "michael.anderson@demofinancehub.com",
  "accounts": [
    {
      "type": "checking",
      "accountNumber": "772004519882",
      "balance": 48221.55
    }
  ],
  "creditScore": 801,
  "kycStatus": "VERIFIED"
}