# Changelog

## [Unreleased]

### Added
- **Global**: Renamed application to "Statement Generation Tool" (对账单生成工具).
- **Billing Config**: 
  - Converted "Add Billing Item" to a controlled Modal.
  - Added new fields: Tax Rate, Default Quantity.
  - Implemented form validation and real-time feedback.
- **Statement Records**:
  - Renamed "Dashboard" to "Statement Records".
  - Refactored data table with Ant Design Table.
  - Added columns: Customer Name, Statement Date, Target Amount, Actual Amount, Match Status, Export Status, Update Time.
  - Added features: Sorting, Filtering, Column Freezing, Batch Export, Pagination, Hover effects.
- **Create Statement**:
  - Changed "Create Statement" workflow to a Step Modal.
  - Steps: Basic Info -> Confirmation.
- **Tech Stack**:
  - Migrated to TypeScript.
  - Integrated Ant Design 5.x.
  - Integrated Styled Components.
  - Added Dark Mode support.

### Changed
- Refactored `App` component to use Ant Design Layout and Menu.
- Updated routing logic.
- Improved accessibility with ARIA attributes and keyboard focus management (via Ant Design).
