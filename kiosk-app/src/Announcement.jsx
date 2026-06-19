// Full-screen kiosk notice. With an image, the photo is the hero (letter-boxed
// so it's never cropped) and any title/body sits in a gradient caption at the
// bottom; text-only notices are shown large and centered.
export default function Announcement({ data }) {
  const { title, body, image_url } = data;
  const hasText = Boolean(title || body);

  if (image_url) {
    return (
      <div className="announce announce--image">
        <img className="announce__img" src={image_url} alt={title || ""} />
        {hasText && (
          <div className="announce__caption">
            {title && <h2 className="announce__title">{title}</h2>}
            {body && <p className="announce__body">{body}</p>}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="announce announce--text">
      {title && <h2 className="announce__title announce__title--big">{title}</h2>}
      {body && <p className="announce__body announce__body--big">{body}</p>}
    </div>
  );
}
