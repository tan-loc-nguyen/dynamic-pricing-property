# BLUE JAY BE API Usage Guide - Reports

> **Superseded on the base URL.** This is an English translation/formatting
> pass over Blue Jay's own vendor document, kept for reference. Its
> `api-test.bluejaypms.com` base URL below is confirmed **wrong** —
> [`docs/BLUEJAY_ENDPOINTS.md`](BLUEJAY_ENDPOINTS.md) is authoritative and
> verified against the live API at `https://api1.bluejaypms.com/api/v2`.
> Treat everything below as the original vendor material being translated,
> not as current guidance — check `BLUEJAY_ENDPOINTS.md` and
> `BLUEJAY_CONTRACT.md` first.

## IMPORTANT - TEST API ACCESS WINDOW

> **Testing API base URL:** `https://api-test.bluejaypms.com/api/v2`
>
> **Blue Jay states that API requests are only allowed during the following testing windows, using Vietnam time (`Asia/Ho_Chi_Minh`, UTC+7):**
>
> - **08:00-08:30 (Vietnam time)**
> - **16:00-16:59 (Vietnam time)**
> - **24:00-24:59 (Vietnam time), as written in the source document**
>
> **Important:** `24:00-24:59` is not standard clock notation. This document preserves the source wording. Confirm with Blue Jay whether this means `00:00-00:59` at the start of the next calendar day before relying on that window.
>
> When testing integrations, schedule API calls inside these allowed windows. Calls outside these windows may fail even when authentication and request parameters are correct.

## Table of Contents

- [Purpose](#purpose)
- [Main Features](#main-features)
  - [1. Filter](#1-filter)
  - [2. Reservation Report](#2-reservation-report)
  - [3. Services - Summary](#3-services---summary)
  - [4. Report - Room - Occupancy](#4-report---room---occupancy)
- [API Address](#api-address)
- [Setup and Authentication](#setup-and-authentication)
- [API Structure](#api-structure)
- [Endpoint Details](#endpoint-details)
  - [1. Filter Endpoints](#1-filter-endpoints)
  - [2. Reservation](#2-reservation)
  - [3. Services - Summary](#3-services---summary-1)
  - [4. Report - Room - Occupancy](#4-report---room---occupancy-1)

## Purpose

This document provides detailed information, rules, and instructions for using APIs provided by **Blue Jay Pos Vietnam**. These APIs are designed to query and retrieve data from the **Blue Jay PMS** system, including:

- Reservation reports
- Booking information
- Service summary reports by group
- Room occupancy reports

## Main Features

### 1. Filter

- **Roomtype - list**: Retrieve the list of room types for a property.
- **Roomdetail - list**: Retrieve the list of physical rooms for a property.
- **Source - list**: Retrieve the list of booking sources for a property.
- **Category - source**: Retrieve the list of source categories for a property.

### 2. Reservation Report

Retrieve reservation/report data.

### 3. Services - Summary

Retrieve service summary data grouped by service category.

### 4. Report - Room - Occupancy

Retrieve room occupancy report data.

> **Source note:** The original document states that the API supports saving payment information into Blue Jay PMS. However, Blue Jay does not participate in payment transactions performed by partners.

## API Address

**Base URL:** `https://api-test.bluejaypms.com/api/v2`

**API key:** The source document contains a concrete API key. It is intentionally not reproduced in this English copy. Use the Blue Jay-provided key through an environment variable or secret manager rather than committing it to source control.

Example environment variable:

```bash
BLUEJAY_API_KEY=your_bluejay_api_key
```

The API key must be sent in the request header for each API request.

> **Testing reminder:** API requests should be made only during the allowed Vietnam-time testing windows shown at the top of this document.

## Setup and Authentication

### Authentication Process

Partners use a unique **API key** issued separately for each Blue Jay customer account. The API key is provided individually to each partner to secure access and separate hotel data.

- Each hotel can only access its own data.
- The **API key** must be included in the **Header** of every API request.

## API Structure

### 1. Supported HTTP Methods

- **GET:** Used to query/retrieve data.
- **POST:** Used to submit new data or perform actions such as creating a booking.

### 2. Data Format

- **Request:** Data sent to the API must use **JSON** format.
- **Response:** The API returns data in **JSON** format.

## Endpoint Details

### 1. Filter Endpoints

**Purpose:** Retrieve room type, physical room, and booking-source information for a property.

#### Get the room type list for `hotelId=1003`

```http
GET https://api-test.bluejaypms.com/api/v2/roomtype-list?hotelId=1003
```

#### Get the physical room list for `hotelId=1003`

```http
GET https://api-test.bluejaypms.com/api/v2/roomdetail-list?hotelId=1003
```

#### Get physical rooms belonging to one room type in `hotelId=1003`

```http
GET https://api-test.bluejaypms.com/api/v2/roomdetail-list?hotelId=1003&roomtypeId=6153
```

#### Get the booking-source category list for `hotelId=1003`

```http
GET https://api-test.bluejaypms.com/api/v2/source-category?hotelId=1003
```

#### Get the booking-source list for `hotelId=1003`

```http
GET https://api-test.bluejaypms.com/api/v2/source-list?hotelId=1003
```

#### Get booking sources in one source category for `hotelId=1003`

```http
GET https://api-test.bluejaypms.com/api/v2/source-list?hotelId=1003&categorySource=2
```

### 2. Reservation

- **Purpose:** Retrieve the reservation list.
- **Request:** `GET https://api-test.bluejaypms.com/api/v2/reservation`
- **HTTP Method:** `GET`

#### Input Parameters

| Property | Data Type | Meaning | Required | Values / Example |
|---|---|---|---|---|
| `hotelId` | int | Hotel ID | Yes | Example: `1003` |
| `dateType` | int | Date type used for filtering | Yes | `0`: check-in date; `1`: check-out date; `2`: booking date; `3`: stay night |
| `from` | datetime | Start date | Yes | Example: `2026-5-21` |
| `to` | datetime | End date | Yes | Example: `2026-5-21` |
| `sources` | string | Source ID(s) | No | Example: `6` |
| `status` | string | Reservation status ID | No | `0`: confirmed; `1`: reserved/held; `2`: no show; `3`: check-in; `4`: check-out; `5`: canceled; `-1`: deleted |
| `roomTypes` | string | Room type ID(s) | No | Example: `6153` |
| `roomdetails` | string | Physical room ID(s) | No | Example: `3` |
| `search` | string | Keyword search | No | Guest name, booking code, or channel code |
| `limit` | int | Number of records per page | No | Default: `20` |
| `page` | int | Page number | No | Default: `1` |

#### Example: Reservations checking in today

```http
GET https://api-test.bluejaypms.com/api/v2/reservation?hotelId=1003&dateType=0&from=2026-5-21&to=2026-5-21
```

#### Example: Reservations checking out today

```http
GET https://api-test.bluejaypms.com/api/v2/reservation?hotelId=1003&dateType=1&from=2026-5-21&to=2026-5-21
```

#### Example: Reservations checking out today for two room types

```http
GET https://api-test.bluejaypms.com/api/v2/reservation?hotelId=1003&dateType=1&from=2026-5-21&to=2026-5-21&roomtypes=6153,6154
```

#### Example: Reservations checking out today for two room types and selected sources

```http
GET https://api-test.bluejaypms.com/api/v2/reservation?hotelId=1003&dateType=1&from=2026-5-21&to=2026-5-21&roomtypes=6153,6154&sources=0,1,3
```

> **Parameter note:** When optional parameters are used, pass their IDs. IDs for `sources`, `roomtypes`, and `roomdetail` are obtained from the corresponding APIs. To request all values, the source document states that `null` should be passed. To pass multiple room types or sources, separate IDs with commas, for example: `&roomtypes=6153,6154&sources=0,1,3`.

#### Top-Level Output Fields

| Property | Data Type | Meaning |
|---|---|---|
| `status` | string | API call status |
| `message` | string | API response message |

#### Sample Response

```json
{
  "meta": {
    "page": 1,
    "limit": 20,
    "total": 15
  },
  "data": {
    "type": "reservation",
    "attributes": {
      "reservations": [
        {
          "bookingCode": "003283",
          "referenceCode": "",
          "guestName": "Ghép đoàn Hà test",
          "roomType": "Holo Ben Thanh - 1 PN",
          "roomName": "H - d3",
          "source": "CTV THƯ",
          "status": "Đã huỷ",
          "bookDate": "2026-05-18 00:00:00",
          "checkInTime": "2026-05-21",
          "arrivalTime": "15:00:00",
          "checkOutTime": "2026-05-22",
          "departureTime": "12:00:00",
          "night": 1,
          "roomPrice": 0,
          "servicePrice": 0,
          "totalPrice": 0,
          "payment": 0,
          "balance": 0,
          "deposit": 0,
          "note": [],
          "guestImagepaper": null
        },
        {
          "bookingCode": "003289",
          "referenceCode": null,
          "guestName": " Ha",
          "roomType": "Căn hộ 3 phòng ngủ",
          "roomName": "B - 2",
          "source": "CTV THƯ",
          "status": "Đã huỷ",
          "bookDate": "2026-05-18 00:00:00",
          "checkInTime": "2026-05-21",
          "arrivalTime": "15:00:00",
          "checkOutTime": "2026-05-22",
          "departureTime": "12:00:00",
          "night": 1,
          "roomPrice": 4725000,
          "servicePrice": 0,
          "totalPrice": 4725000,
          "payment": 4725000,
          "balance": 0,
          "deposit": 0,
          "note": [],
          "guestImagepaper": null
        }
      ]
    }
  }
}
```

#### Response Object

| Property | Data Type | Valid Value / Description | Required |
|---|---|---|---|
| `type` | string | `property` | Yes |
| `attributes` | object | Contains detailed object information | Yes |

#### Reservation Attributes

| Property | Data Type | Meaning |
|---|---|---|
| `bookingCode` | string | Booking code |
| `referenceCode` | string | Channel/reference code |
| `guestName` | string | Guest name |
| `roomType` | string | Room type |
| `roomName` | string | Physical room |
| `source` | string | Booking source |
| `status` | string | Reservation status |
| `bookDate` | datetime | Booking creation date |
| `checkInTime` | datetime | Check-in date |
| `arrivalTime` | timespan | Arrival time |
| `checkOutTime` | datetime | Check-out date |
| `departureTime` | timespan | Departure time |
| `night` | int | Number of nights |
| `roomPrice` | int | Room price |
| `servicePrice` | int | Service price |
| `totalPrice` | int | Total booking price |
| `payment` | int | Amount paid |
| `balance` | int | Remaining balance |
| `deposit` | int | Deposit amount |
| `note` | array | Notes |
| `guestImagepaper` | string | Guest document/image |

### 3. Services - Summary

- **Purpose:** The source document states "retrieve the reservation list" for this endpoint, although the endpoint and response are for service summary data.
- **Request:** `GET https://api-test.bluejaypms.com/api/v2/extraservice-sumary`
- **HTTP Method:** `GET`

#### Input Parameters

| Property | Data Type | Meaning | Required | Values / Example |
|---|---|---|---|---|
| `hotelId` | int | Hotel ID | Yes | Example: `1003` |
| `from` | datetime | Start date | Yes | Example: `2026-5-21` |
| `to` | datetime | End date | Yes | Example: `2026-5-21` |
| `serviceType` | int | Service type | No | `0`: all service types; `5`: in-room service; `6`: out-of-room service |

#### Example: Get all grouped services for `2026-5-21`

```http
GET https://api-test.bluejaypms.com/api/v2/extraservice-sumary?hotelId=1003&from=2026-5-21&to=2026-5-21
```

#### Example: Get all in-room services from `2026-5-1` to `2026-5-9`

```http
GET https://api-test.bluejaypms.com/api/v2/extraservice-sumary?hotelId=1003&serviceType=5&from=2026-5-1&to=2026-5-9
```

#### Output Fields

| Property | Data Type | Meaning |
|---|---|---|
| `status` | string | API call status |
| `message` | string | API response message |

#### Sample Response

```json
{
  "status": "success",
  "message": "Get list extraService Summary successful",
  "data": [
    {
      "GroupService": "Food Type",
      "TotalQuantity": 2,
      "TotalPriceSale": 200000,
      "Service": [
        {
          "ServiceId": 7681,
          "ServiceName": "Cơm chiên bò ",
          "UnitsName": "phần",
          "Quantity": 1,
          "PriceSale": 70000
        },
        {
          "ServiceId": 8111,
          "ServiceName": "Lẩu cá đuối",
          "UnitsName": "phần",
          "Quantity": 1,
          "PriceSale": 130000
        }
      ]
    },
    {
      "GroupService": "Dịch vụ khác",
      "TotalQuantity": 5,
      "TotalPriceSale": 100000,
      "Service": [
        {
          "ServiceId": 1108,
          "ServiceName": "Bò Húc",
          "UnitsName": "lon",
          "Quantity": 5,
          "PriceSale": 100000
        }
      ]
    }
  ]
}
```

### 4. Report - Room - Occupancy

- **Purpose:** The source document states "retrieve the reservation list" for this endpoint.
- **Request:** `GET https://api-test.bluejaypms.com/api/v2/report-room-occupancy`
- **HTTP Method:** `GET`

#### Input Parameters

| Property | Data Type | Meaning | Required | Values / Example |
|---|---|---|---|---|
| `hotelId` | int | Hotel ID | Yes | Example: `1003` |
| `dateType` | int | Aggregation date type | Yes | `1`: day; `2`: month |
| `from` | datetime | Start date | Yes | Example: `2026-5-21` |
| `to` | datetime | End date | Yes | Example: `2026-5-21` |
| `roomtypeIds` | string | Room type ID(s) | No | Example: `6351`; if omitted, all room types are returned |

#### Example from the source: Occupancy for all room types from May 2026 to June 2026, aggregated by month

```http
GET https://api-test.bluejaypms.com/api/v2/reservation?hotelId=1003&dateType=2&from=2026-5&to=2026-6
```

> **Source inconsistency:** The endpoint definition above is `/report-room-occupancy`, but the example in the original document uses `/reservation`. This English version intentionally preserves the example exactly as documented. Verify the correct endpoint with Blue Jay before implementation.

#### Example from the source: Daily occupancy for all room types

```http
GET https://api-test.bluejaypms.com/api/v2/reservation?hotelId=1003&dateType=1&from=2026-5&to=2026-6
```

> **Source inconsistency:** The original text describes a date range of `20/6/2026` to `27/6/2026`, while the example query uses `from=2026-5&to=2026-6`. This is preserved from the source and should be verified with Blue Jay.

> **Monthly-query note:** For monthly data, the source states that `from` defaults to the first day of the starting month and `to` defaults to the last day of the ending month. For example, querying May 2026 through June 2026 is interpreted as `2026-05-01` through `2026-06-30`.

#### Sample Response

```json
{
  "status": "success",
  "message": "Get report room occupancy successful",
  "data": {
    "GrandTotal": {
      "GrandTotalRoomOccupied": 781,
      "GrandTotalBlocked": 36,
      "GrandTotalRoom": 30849,
      "GrandTotalRoomEmpty": 30032,
      "GrandTotalOccupancyRate": 2.53,
      "RoomTypes": [
        {
          "RoomTypeId": 6153,
          "RoomTypeName": "Apartment Double VIP",
          "RoomTypeRoomOccupied": 73,
          "RoomTypeBlocked": 0,
          "RoomTypeTotalRoom": 3003,
          "RoomTypeRoomEmpty": 2970,
          "RoomTypeOccupancyRate": 2.43,
          "DailyDetails": [
            {
              "Date": "01/06/2026",
              "RoomOccupied": 73,
              "Blocked": 0,
              "TotalRoom": 3003,
              "RoomEmpty": 2970,
              "OccupancyRate": 2.43
            },
            {
              "Date": "02/06/2026",
              "RoomOccupied": 73,
              "Blocked": 0,
              "TotalRoom": 3003,
              "RoomEmpty": 2970,
              "OccupancyRate": 2.43
            },
            {
              "Date": "03/06/2026",
              "RoomOccupied": 73,
              "Blocked": 0,
              "TotalRoom": 3003,
              "RoomEmpty": 2970,
              "OccupancyRate": 2.43
            }
          ]
        }
      ]
    }
  }
}
```

## Integration Notes for Developers

1. **Use the testing base URL:** `https://api-test.bluejaypms.com/api/v2`.
2. **Only hit the testing API during Blue Jay's allowed windows in Vietnam time (`Asia/Ho_Chi_Minh`, UTC+7).**
3. Store the API key in an environment variable. Do not hard-code or commit it.
4. Retrieve room type and physical room IDs through the Filter endpoints before building mappings.
5. Reservation `bookDate` is especially relevant for booking-pace calculations.
6. Treat documented endpoint inconsistencies as unresolved until verified against Blue Jay's actual test API.
7. Log request time, endpoint, HTTP status, and sanitized error details during integration testing. Never log the API key.

## Source-Preservation Notes

This English version is a translation and formatting pass over the provided Blue Jay document. It does **not** silently correct ambiguous or inconsistent source material. Where the original document appears inconsistent, the issue is called out explicitly so the implementation team can verify behavior against Blue Jay.
