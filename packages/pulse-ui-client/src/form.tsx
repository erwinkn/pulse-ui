import React, { forwardRef, useCallback, type FormEvent } from "react";

export type PulseFormProps = React.ComponentPropsWithoutRef<"form"> & {
  action: string;
};

/**
 * PulseForm intercepts native form submissions and sends them through fetch so the
 * surrounding Pulse view stays mounted. Server-side handlers are still invoked via
 * the form action endpoint and reactive updates propagate over the socket.
 */
export const PulseForm = forwardRef<HTMLFormElement, PulseFormProps>(
  function PulseForm({ onSubmit, action, ...rest }, ref) {
    return (
      <form
        {...rest}
        action={action}
        ref={ref}
        onSubmit={useCallback(
          (event: FormEvent<HTMLFormElement>) =>
            submitForm({ event, action, onSubmit }),
          [action, onSubmit]
        )}
      />
    );
  }
);

interface SubmitForm {
  event: React.FormEvent<HTMLFormElement>;
  action: string;
  onSubmit?: PulseFormProps["onSubmit"];
  formData?: FormData;
  force?: boolean
}

export async function submitForm({
  event,
  action,
  onSubmit,
  formData,
  force
}: SubmitForm) {
  onSubmit?.(event);
  if (!force && event.defaultPrevented) {
    console.log("Skipping submit because defaultPrevented")
    return;
  }
  const form = event.currentTarget;
  event.preventDefault();
  const nativeEvent = event.nativeEvent as SubmitEvent;
  if (!formData) {
    formData = new FormData(form, nativeEvent.submitter);
  }
  const url = new URL(action, window.location.href);
  try {
    await fetch(url, {
      method: "POST",
      // Required for our hosting scenarios of same host + different ports or 2 subdomains
      credentials: "include",
      body: formData,
    });
  } catch (err) {
    if (process.env.NODE_ENV !== "production") {
      console.error("[Pulse] Form submission failed", err);
    } else {
      throw err;
    }
  }
}
