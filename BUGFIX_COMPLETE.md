# Network Map Bug Fix - COMPLETE ✅

## Original Error
```
'NoneType' object has no attribute 'tag'
```

## Root Causes Fixed

### 1. Missing MAC Field
- `CuemsAvahiListener.update_service()` was missing the `mac` field
- Fixed by adding `'mac': self.get_mac(name)` to the node creation

### 2. XSD Schema Name Mismatch
- **Authoritative XSD** (in cuems-utils) uses element names: `<node_list>` and `<node>`
- **Python classes** were named: `CuemsNodeDict` and `CuemsNode`
- XmlBuilder uses Python class names as XML element names
- **Solution**: Renamed classes to `node_list` and `node`, added backward compatibility aliases

### 3. Missing Custom XML Builders
- The renamed classes (`node_list` and `node`) needed custom XML builders
- XmlBuilder looks for builders in its globals by appending "XmlBuilder" to class name
- **Solution**: Created `NodeXmlBuilders.py` with `node_listXmlBuilder` and `nodeXmlBuilder`
- Registered these builders in XmlBuilder module's globals

### 4. No Validation
- Added validation in `write_network_map()` to catch None values with detailed error messages
- Used `strtobool` from cuemsutils.helpers for consistent boolean parsing

## Files Modified

### Core Files
1. **`CuemsNode.py`** (root and cuemsnodeconf/)
   - Renamed `CuemsNodeDict` → `node_list`
   - Renamed `CuemsNode` → `node`
   - Added backward compatibility aliases
   - Fixed variable naming conflicts in properties

2. **`CuemsAvahiListener.py`** (root and cuemsnodeconf/)
   - Added missing `mac` field in `update_service()`

3. **`CuemsNodeConf.py`** (root and cuemsnodeconf/)
   - Added validation for required fields
   - Used `strtobool` from cuemsutils.helpers
   - Normalized node_type and boolean fields when reading/writing
   - Imported NodeXmlBuilders to register custom builders

4. **`network_map.xsd`** (root and cuemsnodeconf/)
   - Restored authoritative version from cuems-utils
   - **DO NOT modify** - must match cuems-utils version

### New Files
5. **`NodeXmlBuilders.py`** (root and cuemsnodeconf/)
   - Custom XML builders for `node_list` and `node` classes
   - Generates correct `<node_list>` and `<node>` XML tags
   - Registers builders in XmlBuilder module globals

## Test Results
✅ All 58 unit tests pass
✅ All 4 validation tests pass:
- Missing MAC field detection
- Missing UUID field detection  
- Valid node writes successfully
- update_service has mac field

## Deployment

Simply build and install the package:

```bash
cd /path/to/cuems-nodeconf
debuild -b -uc -us -nc
sudo dpkg -i ../cuems-nodeconf_*.deb
sudo systemctl restart cuems-nodeconf
```

## Key Principles Followed

1. **XSD is Authoritative**: Never modify XSD locally - it's shared across CUEMS
2. **Python Class Names Must Match XSD**: XML element names come from class names
3. **Custom Builders for Non-Standard Names**: When class names don't follow PascalCase convention
4. **Boolean Parsing**: Use `strtobool` from cuemsutils.helpers for consistency
5. **Backward Compatibility**: Added aliases so existing imports still work

## What Changed in cuems-utils History

- Commit `d96964d`: XSD used `<CuemsNodeDict>` and `<node>`
- Commit `b57d0eb`: XSD changed to `<node_list>` and `<node>`
- cuems-nodeconf was never updated to match → **This fix addresses that**


