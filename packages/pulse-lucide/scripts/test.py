import pulse as ps
from pulse_lucide import Zap, Plane

print("Zap:", Zap)
print("Plane:", Plane)

print("Registered components:")
for comp in ps.registered_react_components():
    print(f"- {comp}")
