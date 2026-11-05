# Evaluation Results

**Score: 9/10 (90%)**

## Per-document results

| File | Expected | Got | ✓/✗ | Reasons |
|------|----------|-----|-----|---------|
| supplier-pack-01.pdf | Approve | Approve | ✓ |  |
| supplier-pack-02.pdf | Approve | Approve | ✓ |  |
| supplier-pack-03.pdf | Reject | Reject | ✓ | Unit price more than 3% above the maximum |
| supplier-pack-04.pdf | Needs a person | Needs a person | ✓ | Unit price above maximum by no more than 3% |
| supplier-pack-05.pdf | Reject | Reject | ✓ | Item not found in purchase request; Advance payment more than 20% |
| supplier-pack-06.pdf | Reject | Needs a person | ✗ | Penalty clause presence unclear |
| supplier-pack-07.pdf | Needs a person | Needs a person | ✓ | Quote not found in PDF: has_penalty_clause:missing_quote |
| supplier-pack-08.pdf | Reject | Reject | ✓ | Neither TIN nor BIN is present with the correct format |
| supplier-pack-09.pdf | Needs a person | Needs a person | ✓ | Payment terms unclear; Line total does not match quantity × unit price |
| supplier-pack-10.pdf | Reject | Reject | ✓ | Delivery later than 45 days; VAT not shown separately at 15% |

## Confusion matrix

Rows = actual label, columns = predicted label.

| Actual \ Predicted | Approve | Reject | Needs a person |
|---|---|---|---|
| **Approve** | 2 | 0 | 0 |
| **Reject** | 0 | 4 | 1 |
| **Needs a person** | 0 | 0 | 3 |

## Wrong predictions

- **supplier-pack-06.pdf**: expected `Reject`, got `Needs a person`
  - Penalty clause presence unclear
