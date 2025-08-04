import pulse as ps


def counter_page():
  return ps.div(className="w-screen h-screen flex justify-center items-center")[
    ps.h1("Counter demo")
  ]

app = ps.App([ps.Route("/counter", counter_page)])