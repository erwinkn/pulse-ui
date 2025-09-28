
# => DEPRECATED
# Mako template for pre-rendered route pages
# PRERENDERED_ROUTE_TEMPLATE = Template(
#     """import { PulseView } from "${lib_path}/pulse";
# import type { VDOM, ComponentRegistry } from "${lib_path}/vdom";

# % if components:
# // Component imports
# % for component in components:
# % if component.is_default:
# import ${component.tag} from "${component.import_path}";
# % else:
# % if component.alias:
# import { ${component.tag} as ${component.alias} } from "${component.import_path}";
# % else:
# import { ${component.tag} } from "${component.import_path}";
# % endif
# % endif
# % endfor

# // Component registry
# const externalComponents: ComponentRegistry = {
# % for component in components:
#   "${component.key}": ${component.alias or component.tag},
# % endfor
# };
# % else:
# // No components needed for this route
# const externalComponents: ComponentRegistry = {};
# % endif

# // The initial VDOM is bootstrapped from the server
# const initialVDOM: VDOM = ${vdom};

# const path = "${route.unique_path()}";

# export default function RouteComponent() {
#   return (
#     <PulseView
#       initialVDOM={initialVDOM}
#       externalComponents={externalComponents}
#       path={path}
#     />
#   );
# }
# """
# )
