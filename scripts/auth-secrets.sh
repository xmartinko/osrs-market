#!/usr/bin/env bash

set -euo pipefail

script_directory="$(
    cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
    pwd
)"

repository_root="$(
    cd -- "${script_directory}/.."
    pwd
)"

secrets_directory="${repository_root}/.secrets"
auth_environment_file="${secrets_directory}/auth-service.env"
fusionauth_bootstrap_file="${secrets_directory}/fusionauth-bootstrap.env"

kickstart_template_file="${repository_root}/auth/kickstart/kickstart.template.json"
generated_kickstart_file="${secrets_directory}/kickstart.dev.json"
kickstart_renderer="${script_directory}/render-kickstart.py"

command_name="${1:-ensure}"

umask 077

generate_password()
{
    python3 -c '
import secrets
import string

symbols = "!@#$%^&*_-"
alphabet = string.ascii_letters + string.digits + symbols

while True:
    password = "".join(
        secrets.choice(alphabet)
        for _ in range(20)
    )

    if (
        any(character.islower() for character in password)
        and any(character.isupper() for character in password)
        and any(character.isdigit() for character in password)
        and any(character in symbols for character in password)
    ):
        print(password)
        break
'
}


write_bootstrap_file()
{
    local api_key="$1"
    local tenant_id="$2"
    local admin_password="$3"

    local temporary_file

    temporary_file="$(
        mktemp \
            "${secrets_directory}/fusionauth-bootstrap.env.tmp.XXXXXX"
    )"

    {
        printf \
            'FUSIONAUTH_API_KEY=%s\n' \
            "${api_key}"

        printf \
            'FUSIONAUTH_TENANT_ID=%s\n' \
            "${tenant_id}"

        printf \
            'FUSIONAUTH_ADMIN_PASSWORD=%s\n' \
            "${admin_password}"
    } > "${temporary_file}"

    chmod \
        600 \
        "${temporary_file}"

    mv \
        "${temporary_file}" \
        "${fusionauth_bootstrap_file}"

    printf '%s\n' \
        'FUSIONAUTH_ADMIN_EMAIL=admin@example.invalid' \
        'FUSIONAUTH_PUBLIC_URL=http://localhost:9011' \
        'FRONTEND_URL=http://localhost:5173' \
        'FUSIONAUTH_REDIRECT_URI=http://localhost:5173/auth/callback' \
        'FUSIONAUTH_LOGOUT_URL=http://localhost:5173/'
}


ensure_bootstrap_values()
{
    local api_key=""
    local tenant_id=""
    local admin_password=""

    if [[ -f "${fusionauth_bootstrap_file}" ]]
    then
        while IFS='=' read -r key value
        do
            case "${key}" in
                FUSIONAUTH_API_KEY)
                    api_key="${value}"
                    ;;

                FUSIONAUTH_TENANT_ID)
                    tenant_id="${value}"
                    ;;

                FUSIONAUTH_ADMIN_PASSWORD)
                    admin_password="${value}"
                    ;;
            esac
        done < "${fusionauth_bootstrap_file}"
    fi

    if [[ -z "${api_key}" ]]
    then
        api_key="$(
            generate_secret
        )"
    fi

    if [[ -z "${tenant_id}" ]]
    then
        tenant_id="$(
            generate_uuid
        )"
    fi

    if [[ -z "${admin_password}" ]]
    then
        admin_password="$(
            generate_password
        )"
    fi

    write_bootstrap_file \
        "${api_key}" \
        "${tenant_id}" \
        "${admin_password}"
}

fail()
{
    printf \
        'Error: %s\n' \
        "$1" \
        >&2

    exit 1
}


require_command()
{
    command -v "$1" >/dev/null 2>&1 ||
        fail "Required command is missing: $1"
}


prepare_secrets_directory()
{
    mkdir \
        -p \
        "${secrets_directory}"

    chmod \
        700 \
        "${secrets_directory}"
}


read_environment_value()
{
    local requested_key="$1"

    if [[ ! -f "${auth_environment_file}" ]]
    then
        return
    fi

    local key
    local value

    while IFS='=' read -r key value
    do
        if [[ "${key}" == "${requested_key}" ]]
        then
            printf \
                '%s' \
                "${value}"

            return
        fi
    done < "${auth_environment_file}"
}


generate_secret()
{
    openssl rand -hex 32
}


generate_uuid()
{
    if [[ -r /proc/sys/kernel/random/uuid ]]
    then
        tr \
            -d \
            '\r\n' \
            < /proc/sys/kernel/random/uuid

        return
    fi

    fail \
        "Unable to generate a UUID"
}


validate_application_id()
{
    local application_id="$1"

    if [[ ! "${application_id}" =~ ^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$ ]]
    then
        fail \
            "FUSIONAUTH_APPLICATION_ID must be a valid UUID"
    fi
}


validate_client_secret()
{
    local client_secret="$1"

    if [[ -z "${client_secret}" ]]
    then
        fail \
            "FUSIONAUTH_CLIENT_SECRET cannot be empty"
    fi

    if [[ "${client_secret}" == *$'\n'* ]]
    then
        fail \
            "FUSIONAUTH_CLIENT_SECRET cannot contain a newline"
    fi
}


validate_encryption_key()
{
    local encryption_key="$1"

    if (
        ((${#encryption_key} != 64)) ||
        [[ "${encryption_key}" == *[!0-9a-fA-F]* ]]
    )
    then
        fail \
            "TOKEN_ENCRYPTION_KEY must contain exactly 64 hexadecimal characters"
    fi
}


write_environment_file()
{
    local application_id="$1"
    local client_secret="$2"
    local encryption_key="$3"

    local temporary_file

    temporary_file="$(
        mktemp \
            "${secrets_directory}/auth-service.env.tmp.XXXXXX"
    )"

    {
        printf \
            'FUSIONAUTH_APPLICATION_ID=%s\n' \
            "${application_id}"

        printf \
            'FUSIONAUTH_CLIENT_SECRET=%s\n' \
            "${client_secret}"

        printf \
            'TOKEN_ENCRYPTION_KEY=%s\n' \
            "${encryption_key}"
    } > "${temporary_file}"

    chmod \
        600 \
        "${temporary_file}"

    mv \
        "${temporary_file}" \
        "${auth_environment_file}"
}


render_kickstart()
{
    [[ -f "${kickstart_template_file}" ]] ||
        fail \
            "Kickstart template not found: ${kickstart_template_file}"

    [[ -f "${kickstart_renderer}" ]] ||
        fail \
            "Kickstart renderer not found: ${kickstart_renderer}"

    local temporary_file

    temporary_file="$(
        mktemp \
            "${secrets_directory}/kickstart.tmp.XXXXXX"
    )"

    if ! python3 \
        "${kickstart_renderer}" \
        "${auth_environment_file}" \
        "${fusionauth_bootstrap_file}" \
        "${kickstart_template_file}" \
        "${temporary_file}"
    then
        rm \
            -f \
            "${temporary_file}"

        fail \
            "Unable to render the FusionAuth Kickstart file"
    fi

    chmod \
        600 \
        "${temporary_file}"

    mv \
        "${temporary_file}" \
        "${generated_kickstart_file}"
}


save_configuration()
{
    local application_id="$1"
    local client_secret="$2"
    local encryption_key="$3"

    validate_application_id \
        "${application_id}"

    validate_client_secret \
        "${client_secret}"

    validate_encryption_key \
        "${encryption_key}"

    write_environment_file \
        "${application_id}" \
        "${client_secret}" \
        "${encryption_key}"

    ensure_bootstrap_values

    render_kickstart
}


ensure_secrets()
{
    prepare_secrets_directory

    local application_id
    local client_secret
    local encryption_key

    local application_id_generated="false"
    local client_secret_generated="false"
    local encryption_key_generated="false"

    application_id="$(
        read_environment_value \
            "FUSIONAUTH_APPLICATION_ID"
    )"

    client_secret="$(
        read_environment_value \
            "FUSIONAUTH_CLIENT_SECRET"
    )"

    encryption_key="$(
        read_environment_value \
            "TOKEN_ENCRYPTION_KEY"
    )"

    if [[ -z "${application_id}" ]]
    then
        application_id="$(
            generate_uuid
        )"

        application_id_generated="true"
    fi

    if [[ -z "${client_secret}" ]]
    then
        client_secret="$(
            generate_secret
        )"

        client_secret_generated="true"
    fi

    if [[ -z "${encryption_key}" ]]
    then
        encryption_key="$(
            generate_secret
        )"

        encryption_key_generated="true"
    fi

    save_configuration \
        "${application_id}" \
        "${client_secret}" \
        "${encryption_key}"

    printf \
        'Authentication configuration is ready.\n'

    printf \
        'Environment: %s\n' \
        "${auth_environment_file}"

    printf \
        'Kickstart:  %s\n' \
        "${generated_kickstart_file}"

    if [[ "${application_id_generated}" == "true" ]]
    then
        printf \
            'Generated a new FusionAuth application ID.\n'
    fi

    if [[ "${client_secret_generated}" == "true" ]]
    then
        printf \
            'Generated a new FusionAuth client secret.\n'
    fi

    if [[ "${encryption_key_generated}" == "true" ]]
    then
        printf \
            'Generated a new token-encryption key.\n'
    fi
}


configure_existing()
{
    prepare_secrets_directory

    local application_id
    local client_secret
    local encryption_key

    read \
        -r \
        -p "FusionAuth application ID: " \
        application_id

    read \
        -r \
        -s \
        -p "FusionAuth client secret: " \
        client_secret

    printf '\n'

    encryption_key="$(
        read_environment_value \
            "TOKEN_ENCRYPTION_KEY"
    )"

    if [[ -z "${encryption_key}" ]]
    then
        encryption_key="$(
            generate_secret
        )"
    fi

    save_configuration \
        "${application_id}" \
        "${client_secret}" \
        "${encryption_key}"

    unset client_secret

    printf \
        'Existing FusionAuth configuration saved.\n'
}


require_command \
    "openssl"

require_command \
    "python3"

case "${command_name}" in
    ensure)
        ensure_secrets
        ;;

    configure-existing)
        configure_existing
        ;;

    *)
        fail \
            "Usage: $0 {ensure|configure-existing}"
        ;;
esac