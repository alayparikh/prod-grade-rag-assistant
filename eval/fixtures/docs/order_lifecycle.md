# Order Lifecycle

Every Acme order moves through the statuses below. The status shown to customers and in the orders database is always one of these values.

## placed

The order has been received and payment or credit terms are confirmed. Orders normally stay in placed for one business day before picking starts.

## picking

The robots are being pulled from stock, configured with the customer's site map and packed. Picking normally takes two to four business days; PR-900 units take longer because each is load-tested first.

## shipped

The order has left the Acme warehouse and has a carrier tracking number. Transit time depends on the region, as set out in the shipping policy.

## delivered

The carrier has confirmed delivery and the customer's site contact has signed for it. Commissioning on site is scheduled separately by the deployment team.

## on_hold

The order is paused and will not move to the next status until the hold is cleared. Every on_hold order has a hold_reason; the shipping policy describes each reason and how to resolve it. An order on hold past its promised delivery date counts as late.

## cancelled

The order was cancelled before shipping. Cancellations after picking has started incur a 5% re-stocking charge.

## returned

The robots were sent back after delivery under the returns and warranty policy, and the order is closed.
