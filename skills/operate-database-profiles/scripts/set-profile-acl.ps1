param(
    [switch]$Check,

    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Path
)

$ErrorActionPreference = 'Stop'

$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$directory = [System.IO.DirectoryInfo]::new($Path)

if ($directory.Exists -and (($directory.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0)) {
    throw 'Profile root cannot be a reparse point.'
}

if ($Check) {
    if (-not $directory.Exists) {
        exit 1
    }

    $currentAcl = $directory.GetAccessControl()
    $owner = $currentAcl.GetOwner([System.Security.Principal.SecurityIdentifier])
    if (-not $currentAcl.AreAccessRulesProtected -or $owner.Value -ne $identity.Value) {
        exit 1
    }

    $rules = $currentAcl.GetAccessRules(
        $true,
        $true,
        [System.Security.Principal.SecurityIdentifier]
    )
    $hasFullControl = $false
    foreach ($currentRule in $rules) {
        if (
            $currentRule.IdentityReference.Value -ne $identity.Value -or
            $currentRule.AccessControlType -ne [System.Security.AccessControl.AccessControlType]::Allow
        ) {
            exit 1
        }
        if (
            ($currentRule.FileSystemRights -band [System.Security.AccessControl.FileSystemRights]::FullControl) -eq
            [System.Security.AccessControl.FileSystemRights]::FullControl
        ) {
            $hasFullControl = $true
        }
    }

    if (-not $hasFullControl) {
        exit 1
    }
    exit 0
}

$directory = [System.IO.Directory]::CreateDirectory($Path)
$acl = New-Object System.Security.AccessControl.DirectorySecurity
$acl.SetOwner($identity)
$acl.SetAccessRuleProtection($true, $false)
$rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
    $identity,
    [System.Security.AccessControl.FileSystemRights]::FullControl,
    [System.Security.AccessControl.InheritanceFlags]'ContainerInherit, ObjectInherit',
    [System.Security.AccessControl.PropagationFlags]::None,
    [System.Security.AccessControl.AccessControlType]::Allow
)
$acl.AddAccessRule($rule)
$directory.SetAccessControl($acl)
