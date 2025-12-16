# BART fleet-aware train length and frequency planning

## Overview

Let's put ourselves in the shoes of the "BART Manager". Suppose this individual has only
two levers to pull and adjust the BART system:

1. **Frequency:** How often do we run a train? (Every 6 minutes, 15 minutes)
2. **Train Length:** How big is each train? (4-car or 10-car?)

BART has 5 lines (Red, Orange, Yellow, Blue Green), and offers service from 6am until
midnight. The two problems that we would like to solve are:

1. **Meet Demand:** We want to ensure that people don't get left behind at each
station.
2. **As few cars as possible:** We own a specific number of cars. If we run
10-car trains every 2 minutes on every line, we would run out of cars instantly.

Within this framework, across every single BART line, and time period, is it possible to
find the perfect frequency (times / hour) and length of trains so **the fewest people
get left behind** and we use the **fewest possible number of cars**?

## Basic Assumptions

1. There are 5 lines $l \in L = \{\text{RED, ORANGE, YELLOW, BLUE, GREEN}\}$
2. There are 4 time periods $p \in P = \{\text{AM, PM, MID, EVE}\}$
3. There are 7 possible train lengths $k \in K = \{3, 4, 5, 6, 7, 8, 9, 10\}$

## Definitions

1. **OD:** Origin-Destination. This is the way the demand data is given to us
2. **Segment:** A specific line between two adjacent stations. For example,
Downtown Berkeley to Ashby would be a segment

## Decision Variables

All of these variables are defined for a single line, in a single time period, for a
single train length.

1. Frequency (trains per hour): $f_{l, p, k}$
2. Unmet Demand (passengers that can't make the train for a segment): $U_{p}$

> [!note]
> The unmet demand is only calculated at the time period level. For a specific time,
> which passengers are unable to make that specific segment due to some other constraint

## Objective

We're going to use a technique called Lexicographic Optimization to deal with the fact
that we are trying to solve multiple optimizatino problems. The central idea here is to
arrange the optimization problem in an order of importance, where the first problem's
output becomes an input (as a constraint) into the next problem, and so on...

In our case, we've got two problems that we'll solve in the following order.

**1. Minimize Unmet Demand**

For each segment, we're going to try and find the smallest possible unmet demand that we
can accomplish. Note that we're still going to generate values for our other decision
variable $f_{l,p,k}$, but we'll ignore those values for now and focus on the objective
value of unmet demand: $U$

The constraint: $$\text{Capacity}_{ij,p} + u_{ij,p} \ge \text{Demand}_{ij,p}$$

**2. Minimize Fleet Usage**

Now, we add a constraint from (1), which is that total unmet demand must be less than
$U$, and resolve the optimization problem to generate the optimal values of $f_{l,p,k}$

So, this would give us the best possible allocation of cars and frequencies across BART
to ensure we are able to cover the total demand per segment within some acceptable unmet
demand.

## Constraints

There are two major constraints we need to deal with.

### 1. Demand for each segment

The data file we're using to derive this lists the total number of swipes within an hour
between every single origin-destination (OD) pair, as such:

| From | To | Hour | Swipes | 
| ---  | -- | ---- | ------ |
| OAK | SFO | 0 | 10 | 
| ... and so on | | | |

The problem with this file is that it doesn't give us the demand for a single segment,
we will have to derive that. We're gonna do it via a process called "routing"

**Routing:** For a given segment, how many OD pairs pass through that specific segment
at thtat specific hour? The sum total of that number represents the total amount of 
capacity that the train would have to account for

The constraint:

### 2. Fleet size

The BART has a total of 1,100 cars which it needs to distribute across this entire network. 
We need to first evaluate how many total cars our $f_{l,p,k}$ decision variables are
allocating across the network. We can estimate this using the following formula:

Cars Needed = Frequency x Round Trip x Train Length

Suppose we assigned $f_{\text{RED, AM, 3}} = 1$ = The red line in the morning as 1 3-car
train. Further suppose that a round trip lasts 2 hours. Then, we'd need a total of 6
cars to support this schedule for the red line in the morning. 

The constraint: $$\sum_{l \in L} \sum_{k \in K} cars_{l, p, k} \le 1100$$

### 3. Laws of Physics

We fundamentally must ensure there is a gap of at least 5 minutes between trains, and not more than 30 minutes.
We need to translate this into number of trains per hour

The constraint: $$2 \le \sum_{k \in K} f_{l,p,k} \le 12$$