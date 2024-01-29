# Microsoft Dynamics 365 Finance & Operations Data Source

Microsoft Dynamics 365 for Finance and Operations is an enterprise resource planning (ERP) solution developed by
Microsoft. It is designed to help enterprises manage critical business functions such as finance, accounting,
production, warehousing, and transportation management.

This connector uses the [OData service](https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/data-entities/odata) to query the finance and operations (FO) entities.


# Functionality

The extractor uses the [OData service](https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/data-entities/odata) to download data from the O365 FO.

# Configuration

## Authorization

Authorize the component with the account that has access to OData entities. Admin privileges might be needed to access some datasets.

### Admin consent

In some cases, you will need to provide admin consent to our application in your Azure Portal. See [these instructions](https://learn.microsoft.com/en-us/entra/identity/enterprise-apps/grant-admin-consent?pivots=portal#grant-tenant-wide-admin-consent-in-enterprise-apps) 
for more information. 

**To grant consent, follow these steps:**

1. Sign in to the [Microsoft Entra admin center](https://entra.microsoft.com/) as at least a [Cloud Application Administrator](https://learn.microsoft.com/en-us/entra/identity/role-based-access-control/permissions-reference#cloud-application-administrator).
2. Browse to **Identity > Applications > Enterprise applications > All applications**.
3. Enter the name of the application **`Dynamics 365 - FO`** or search by Application ID **`c99979ef-d0fe-49fe-9d64-c91b275094d8`**.
4. Select **Permissions** under **Security**. The screenshot shows how to grant tenant-wide admin consent.
![screen](https://learn.microsoft.com/en-us/entra/identity/enterprise-apps/media/grant-tenant-wide-admin-consent/grant-tenant-wide-admin-consent.png)

5. Carefully review the permissions that the application requires. If you agree with them, select **Grant admin consent**.

## Row setup

1. Select the desired endpoint.
2. (Optional) If required, filter only selected columns.
3. (Optional) Define the OData request query. This is an expert option to provide more flexibility; use it at your own risk. All query pieces can be separated by a newline or "&". Please refer to [this article](https://docs.oasis-open.org/odata/odata/v4.0/errata03/os/complete/part1-protocol/odata-v4.0-errata03-os-part1-protocol-complete.html#_The_$filter_System) on how to use the Odata filter.


### Destination / Output
- Optionally, fill in the name of the result table. This will be the name of the result table in Storage. Make sure that each configuration row leads to a different table to prevent any conflicts. If left empty, the dataset name is used.
- Select `Load type`. Choose between `Full load` and `Incremental load`. If full load is used, the destination table will be overwritten with every run. If incremental load is used, data will be upserted into the destination table.



# Development

If required, change the local data folder (the `CUSTOM_FOLDER` placeholder) path to your custom path in the docker-compose file:

```yaml
    volumes:
      - ./:/code
      - ./CUSTOM_FOLDER:/data
```

Clone this repository, init the workspace, and run the component with the following command:

```
git clone repo_path my-new-component
cd my-new-component
docker-compose build
docker-compose run --rm dev
```

Run the test suite and lint check using this command:

```
docker-compose run --rm test
```

# Integration

tbd